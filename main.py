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
from OrderManager import OrderManager
# from Order import Order

# TODO: Backup
# TODO: Log
# TODO: delete paid invoices from CLN and copy data to rektBot.log

logging.addLevelName(15, "DEBG")
DEB = 15

log = logging.getLogger()
log.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('rektBot.log')
file_handler.setLevel(15)
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
    new_order = Signal(object)
    set_order_paid = Signal(object)
    set_order_unpaid = Signal(object)
    set_order_expired = Signal(object)
    set_order_funding = Signal(object)
    set_order_funded = Signal(object)
    set_order_funding_fail = Signal(object)
    set_order_open = Signal(object)
    set_order_close = Signal(object)
    del_order = Signal(object)

    def __init__(self, pk):
        QObject.__init__(self)

        #  Quit application on CTRL + C
        signal.signal(signal.SIGINT, self.interupt)

        # TODO: periodicaly check stopped workers in list and delete them
        self.worker_list = []

        self.loop_worker = Worker(self.loop)

        self.private_key = PrivateKey.from_nsec(pk)
        self.relay_manager = None
        log.info('Start NostrBot')
        log.info(f'Using pubkey {self.private_key.public_key.bech32()}')

        self.lnm = LNMarkets(config.lnmarkets['key'], config.lnmarkets['secret'], config.lnmarkets['passphrase'])

        self.order_manager = OrderManager()
        self.order_manager.order_status_new.connect(self.on_new_order)
        self.order_manager.order_status_unpaid.connect(self.on_unpaid)
        self.order_manager.order_status_paid.connect(self.on_paid)
        self.order_manager.order_status_expired.connect(self.on_expired)
        self.order_manager.order_status_funding.connect(self.on_funding)
        self.order_manager.order_status_funding_fail.connect(self.on_funding_fail)
        self.order_manager.order_status_funded.connect(self.on_funded)
        self.order_manager.order_status_open.connect(self.on_open)
        self.order_manager.order_status_close.connect(self.on_close)
        self.order_manager.order_status_deleted.connect(self.on_deleted)

        self.new_order.connect(self.order_manager.new_order)
        self.set_order_unpaid.connect(self.order_manager.set_order_unpaid)
        self.set_order_paid.connect(self.order_manager.set_order_paid)
        self.set_order_expired.connect(self.order_manager.set_order_expired)
        self.set_order_funding.connect(self.order_manager.set_order_funding)
        self.set_order_funded.connect(self.order_manager.set_order_funded)
        self.set_order_funding_fail.connect(self.order_manager.set_order_funding_fail)
        self.set_order_open.connect(self.order_manager.set_order_open)
        self.set_order_close.connect(self.order_manager.set_order_close)
        self.del_order.connect(self.order_manager.del_order)

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
        log.log(15,f"Publish message to all relays({msg})")
        for relay in self.relay_manager.relays.values():
            if relay.policy.should_write:
                relay.publish(msg)

    def reply_to(self, note_id, user, msg: str):
        reply = Event(content=msg)
        log.info(f"Reply to note {note_id[:5]}_{note_id[-5:]} from user {user[:5]}_{user[-5:]}")
        log.log(15,f"Message: {msg}")
        # create 'e' tag reference to the note you're replying to
        reply.add_event_ref(note_id)

        # create 'p' tag reference to the pubkey you're replying to
        reply.add_pubkey_ref(user)

        self.private_key.sign_event(reply)
        self.relay_manager.publish_event(reply)

    def loop(self, *args, **kwargs):
        while True:
            self.listen_notifications()
            self.check_unpaid_orders()
            self.check_open_orders()
            time.sleep(1)

    def listen_notifications(self):
        while self.relay_manager.message_pool.has_events():
            event_msg = self.relay_manager.message_pool.get_event()
            self.handle_event(event_msg.event.to_json()[1])

    def check_unpaid_orders(self):
        unpaid_orders = self.order_manager.list_unpaid_orders()

        for order in unpaid_orders:
            status = RPC.invoice_status(order.order_id)
            if status == 'paid':
                self.set_order_paid.emit(order.order_id)
            elif status == 'expired':
                self.set_order_expired.emit(order.order_id)

    def check_open_orders(self):
        open_orders = self.order_manager.list_open_orders()

        for order in open_orders:
            # TODO: check order state on LNM
            pass

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

    # Handle notification
    def handle_event(self, event):
        if not self.in_history(event['id']):
            log.info(f"Get notification")
            log.log(15,f"Event:{event}")

            note_id = event['id']
            note_from = event['pubkey']
            note_content = event['content'].lower()

            #  If long or short in content
            if ' long ' or ' short ' in note_content:
                log.log(15,"LONG or SHORT command detected in content")
                pattern_long = r'\blong\s+(\d+)\b'
                pattern_short = r'\bshort\s+(\d+)\b'
                pattern_leverage = r'\bx(\d+)\b'
                pattern_tp = r'\btp(\d+)\b'
                
                # Parse params
                if ('long' in note_content) and ('short' in note_content):
                    log.log(15,"Both short AND long command in content, return")
                    return
                elif 'long' in note_content:
                    log.log(15,"Command is LONG")
                    amount = re.findall(pattern_long, note_content)
                    order_type = 'long'
                elif 'short' in note_content:
                    log.log(15,"Command is SHORT")
                    amount = re.findall(pattern_short, note_content)
                    order_type = 'short'
                else:
                    log.log(15,"Command is unknow")
                    return
                
                leverage = re.findall(pattern_leverage, note_content)
                if not leverage:
                    leverage = 1
                else:
                    leverage = int(leverage[0])
                log.log(15,f"{leverage=}")
                
                tp = re.findall(pattern_tp, note_content)
                
                #  Open order
                log.log(15, f"{amount=}, {tp=}")
                if amount and tp:

                    amount = int(amount[0])
                    tp = int(tp[0])

                    log.log(15,f"{order_type=}, {amount=}, {leverage=}, {tp=}")
                    log.info(f'[{note_id[:5]}_{note_id[-5:]}] {note_from[:5]}_{note_from[-5:]} request for LONG {amount} sats')
                    self.new_order.emit({'order_id': note_id,
                                         'user': note_from,
                                         'amount': amount,
                                         'order_type': order_type,
                                         'tp': tp,
                                         'leverage': leverage,
                                         })

    def on_new_order(self, order):
        invoice = RPC.invoice(order.amount, order.order_id)
        log.info('Generate invoice')
        log.log(15,f'invoice: {invoice}')
        self.set_order_unpaid.emit({'order_id': order.order_id, 'invoice': invoice,})
        
    def on_unpaid(self, order):
        self.reply_to(order.order_id, order.user, order.invoice)
    
    def on_paid(self, order):
        log.info(f"Received payment for invoice {order.order_id[:5]}_{order.order_id[-5:]}")
        self.reply_to(order.order_id, order.user, f"I receive your {order.amount} sats, you'll be rekt soon!")
        self.set_order_funding.emit(order.order_id)
    
    def on_expired(self, order):
        pass
    
    def on_funding(self, order):
        self.detach_send_funds_to_lnm(order)
    
    def on_funded(self, order):
        log.info(f'Funding success for invoice {order.order_id[:5]}_{order.order_id[-5:]}')
        # TODO: Open trade
        #self.set_order_open.emit({'order_id': order.order_id, 'price': open_price})

    def on_funding_fail(self, order):
        log.info(f'Funding fail for invoice {order.order_id[:5]}_{order.order_id[-5:]}')
        #  TODO: implement refund
        #  TODO: notify admin

    def on_open(self, order):
        log.info(f'Trade open at {order.open_price} for order {order.order_id[:5]}_{order.order_id[-5:]}')
    
    def on_close(self, order):
        log.info(f'Trade close at {order.close_price} for order {order.order_id[:5]}_{order.order_id[-5:]}')

    def on_deleted(self, order):
        pass

    def detach_send_funds_to_lnm(self, order):
        order = copy(order)
        worker = Worker(self.send_funds_to_lnm)
        self.worker_list.append(worker)
        worker.args = (order,)
        worker.result.connect(self.after_detach_send)
        worker.start()

    def send_funds_to_lnm(self, order) -> dict:
        amount = order.amount
        invoice = self.lnm.deposit_invoice(amount)
        success = False
        for i in range(5):
            if RPC.pay_invoice(invoice):
                success = True
                break

        if not success:
            log.info('LNM funding Fail')
            return {
                'order': order,
                'send': False,
                }
        else:
            log.info("LNM funding Success")
            return {
                'order': order,
                'send': True,
            }

    def after_detach_send(self, ret):
        order = ret['order']
        send = ret['send']

        if not send:
            self.set_order_funding_fail.emit(order.order_id)
        else:
            self.set_order_funded.emit(order.order_id)


app = QCoreApplication()
bot = NostrBot(config.key)
bot.loop_worker.start()

app.exec()

sys.exit(0)



