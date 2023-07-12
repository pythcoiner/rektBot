import logging
import re
import config
import subprocess
from copy import deepcopy as copy
import signal
import sys

from nostr.key import PrivateKey, PublicKey
import json
import ssl
import time
from nostr.filter import Filter, Filters
from nostr.event import Event, EventKind
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType

from PySide6.QtCore import QThread, QObject, Signal
from PySide6.QtCore import QCoreApplication

from RPC import RPC
from LNM import LNMarkets
from Order import Order

# TODO: Backup
# TODO: Log
# TODO: delete paid invoices from CLN and copy data to rektBot.log

log = logging.getLogger()
log.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('rektBot.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

log.addHandler(file_handler)
log.addHandler(stream_handler)


class Worker(QThread):

    result = Signal(object)

    def __init__(self, function, args=(), kwargs={}):
        QThread.__init__(self)
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        args = self.args
        kwargs = self.kwargs
        out = self.function(*args, **kwargs)
        self.result.emit(out)


class NostrBot(QObject):

    def __init__(self, pk):
        QObject.__init__(self)

        #  Quit application on CTRL + C
        signal.signal(signal.SIGINT, self.interupt)

        self.loop_worker = Worker(self.loop)

        self.private_key = PrivateKey.from_nsec(pk)
        self.relay_manager = None
        log.info('Start NostrBot')
        log.info(f'Using pubkey {self.private_key.public_key.bech32()}')

        self.lnm = LNMarkets(config.lnmarkets['key'], config.lnmarkets['secret'], config.lnmarkets['passphrase'])

        self.order_list = []
        self.load_orders()
        log.info(f"Order list length {len(self.order_list)}")

        self.connect_relays()

    def interupt(self, a, b):
        sys.exit()

    def start(self):
        self.loop_worker.start()

    def connect_relays(self):
        self.relay_manager = RelayManager()
        log.info("Add relay wss://nostr.oxtr.dev")
        self.relay_manager.add_relay("wss://nostr.oxtr.dev")
        log.info("Add relay wss://nostr.mom")
        self.relay_manager.add_relay("wss://nostr.mom")
        log.info("Add relay wss://relay.damus.io")
        self.relay_manager.add_relay("wss://relay.damus.io")

        # Register to npub notifications
        npub = self.private_key.public_key.hex()
        filters = Filters([Filter(pubkey_refs=[npub]
                                  , kinds=[EventKind.TEXT_NOTE])])
        log.info(f"Register for notification on pubkey {self.private_key.public_key.bech32()}")
        self.relay_manager.add_subscription_on_all_relays('rektbot', filters)

        request = [ClientMessageType.REQUEST, 'rektbot']
        request.extend(filters.to_json_array())
        message = json.dumps(request)
        self.publish_to_all_relays(message)
        time.sleep(0.25)  # allow the messages to send

    def publish_to_all_relays(self, msg):
        log.debug(f"Publish message to all relays({msg})")
        for relay in self.relay_manager.relays.values():
            if relay.policy.should_write:
                relay.publish(msg)

    def reply_to(self, note_id, user, msg: str):
        reply = Event(content=msg)
        log.info(f"Reply to note {note_id[:5]}_{note_id[-5:]} from user {user[:5]}_{user[-5:]}")
        log.debug(f"Message: {msg}")
        # create 'e' tag reference to the note you're replying to
        reply.add_event_ref(note_id)

        # create 'p' tag reference to the pubkey you're replying to
        reply.add_pubkey_ref(user)

        self.private_key.sign_event(reply)
        self.relay_manager.publish_event(reply)

    def loop(self, *args, **kwargs):
        while True:
            self.listen_notifications()
            self.update_orders()
            time.sleep(1)

    def listen_notifications(self):
        while self.relay_manager.message_pool.has_events():
            event_msg = self.relay_manager.message_pool.get_event()
            self.handle_event(event_msg.event.to_json()[1])

    def update_orders(self):
        #  handle the status change
        for i in range(len(self.order_list)):
            order = self.order_list[i]
            label = order.id
            previous_status = order.status

            #  Handle unpaid => (paid|expired)
            if previous_status == 'unpaid':
                status = RPC.invoice_status(label)
                #  Status have changed
                if status != 'unpaid':

                    self.order_list[i].status = status

                    if status == 'paid':
                        #  Notify user on nostr
                        log.info(f"Received payment for invoice {label[:5]}_{label[-5:]}")
                        self.reply_to(label, order.user
                                      , f"I receive your {order.amount} sats, you'll be rekt soon!")

                        #  Transfer funds to LNMarkets
                        send = self.send_funds_to_lnm(order.amount)
                        if not send:
                            log.info(f'Refund process for invoice {label[:5]}_{label[-5:]}')
                            #  TODO: implement refund process
                            #  TODO: Notify admin (nostr?mail?)

                        #  Place order

                        #  Notify user on nostr

                    elif status == 'expired':
                        log.info(f"Invoice {label[:5]}_{label[-5:]} expired")

        # delete expired/deleted orders
        order_list = copy(self.order_list)

        buffer = []
        for order in order_list:
            if order.status not in ['expired', 'invoice_not_exist']:
                buffer.append(order)
            else:
                label = order.id
                status = order.status
                log.debug(f"Invoice {label[:5]}_{label[-5:]} deleted from list: {status}")
                RPC.del_invoice(label, status)

        self.order_list = buffer

        self.save_orders()

    @staticmethod
    def in_history(hash) -> bool:
        hash += '\n'
        file = open('history', 'r')
        note_history = file.readlines()
        file.close()
        if hash in note_history:
            return True
        else:
            file = open('history', 'a')
            file.write(hash)
            file.close()
            return False

    def handle_event(self, event):
        if not self.in_history(event['id']):
            log.info(f"Get notification")
            log.debug(f"Event:{event}")

            note_id = event['id']
            note_from = event['pubkey']
            note_content = event['content']

            if ' long ' in event['content']:
                log.debug("notification is for LONG")
                pattern = r'\blong\s+(\d+)\b'

                amount = re.findall(pattern, note_content)
                if amount:
                    amount = amount[0]
                    log.debug(f"Amount found: {amount}")
                    log.info(f'[{note_id[:5]}_{note_id[-5:]}] {note_from[:5]}_{note_from[-5:]} request for LONG {amount} sats')
                    invoice = RPC.invoice(amount, note_id)
                    log.info('Generate invoice')
                    log.debug(f'Invoice: {invoice}')
                    self.reply_to(note_id, note_from, invoice)
                    self.create_order(note_id, note_from, 'long', amount, invoice)

    def create_order(self, id, user, type, amount, invoice) -> str:
        status = 'unpaid'
        profit = '0'
        raw_order = f"{id}:{user}:{type}:{amount}:{status}:{profit}:{invoice}:\n"
        order = Order.from_string(raw_order)
        self.order_list.append(order)
        self.save_orders()


        return invoice
    
    def load_orders(self):
        self.order_list = []
        file = open('orders', 'r')
        orders = file.readlines()
        for i in orders:
            self.order_list.append(Order.from_string(i))

    def save_orders(self):
        file = open('orders', 'w')
        for i in self.order_list:
            file.write(i.to_string())

    def send_funds_to_lnm(self, amount) -> bool:

        invoice = self.lnm.deposit_invoice(amount)
        success = False
        for i in range(5):
            if RPC.pay_invoice(invoice):
                success = True
                break

        if not success:
            log.info('LNM funding Fail')
            return False
        else:
            log.info("LNM funding Success")
            return True


app = QCoreApplication()
bot = NostrBot(config.key)
bot.loop_worker.start()

app.exec()

sys.exit(0)



