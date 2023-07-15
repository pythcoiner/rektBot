import logging
import re
import config
import subprocess
from copy import deepcopy as copy
import signal
import sys
import random
import math

import json
import ssl
import time
from nostr.key import PrivateKey, PublicKey
from nostr.filter import Filter, Filters
from nostr.event import Event, EventKind, EncryptedDirectMessage
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType

from PySide6.QtCore import QThread, QObject, Signal
from PySide6.QtCore import QCoreApplication

from RPC import RPC
from LNM import LNMarkets
from OrderManager import OrderManager
from lud_16 import LUD16


# TODO: charge for withdraw fee??
# TODO: cannot parse invoice from Phoenix
# TODO: use stable LUD16 implementation
# TODO: how to check that LNM deposit invoice expired?
# TODO: if open order fail handle refund
# TODO: control max outbound fee on CLN


# TODO: add close function
# TODO: Backup
# TODO: Cleaner Log []
# TODO: DB recovery log
# TODO: delete paid invoices from CLN and copy data to rektBot.log
# TODO: handle every case when API call not success
# TODO: move history to a peewee DB

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
        self.data = None

    def run(self):
        args = self.args
        kwargs = self.kwargs
        out = self.function(*args, **kwargs)
        data = {'data': self.data, 'return': out}
        self.result.emit(data)


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
    set_order_withdraw_requested = Signal(object)
    set_order_withdraw_receive_invoice = Signal(object)
    set_order_withdraw_done = Signal(object)
    set_order_status_withdraw_fail = Signal(object)
    del_order = Signal(object)

    def __init__(self, pk):
        QObject.__init__(self)

        #  Quit application on CTRL + C
        signal.signal(signal.SIGINT, self.interupt)

        self.private_key = PrivateKey.from_nsec(pk)
        # print(self.private_key.bech32())

        # TODO: periodicaly check stopped workers in list and delete them
        self.worker_list = []
        self.users_list = []
        self.lnurl_list = {}

        self.filters = None
        self.relay_manager = None

        self.connect_relays()
        self.update_filters()

        self.loop_worker = Worker(self.loop)

        log.info('Start NostrBot')
        log.info(f'Using pubkey {self.private_key.public_key.bech32()}')

        self.fee = 0.002

        key = config.lnmarkets['key']
        secret = config.lnmarkets['secret']
        passphrase = config.lnmarkets['passphrase']
        self.lnm = LNMarkets(key, secret, passphrase, self.fee)

        self.order_manager = OrderManager()
        self.order_manager.order_status_new.connect(self.on_new_order)
        self.order_manager.order_status_unpaid.connect(self.on_unpaid)
        # self.order_manager.order_status_paid.connect(self.on_paid)
        self.order_manager.order_status_expired.connect(self.on_expired)
        self.order_manager.order_status_funding.connect(self.on_funding)
        self.order_manager.order_status_funding_fail.connect(self.on_funding_fail)
        # self.order_manager.order_status_funded.connect(self.on_funded)
        self.order_manager.order_status_paid.connect(self.on_funded)
        self.order_manager.order_status_open.connect(self.on_open)
        self.order_manager.order_status_close.connect(self.on_close)
        self.order_manager.order_status_withdraw_requested.connect(self.on_withdraw_requested)
        self.order_manager.order_status_withdraw_done.connect(self.on_withdraw_done)
        self.order_manager.order_withdraw_notify_amount.connect(self.on_withdraw_notify_amount)
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
        self.set_order_withdraw_requested.connect(self.order_manager.set_order_withdraw_requested)
        self.set_order_withdraw_receive_invoice.connect(self.order_manager.set_order_withdraw_receive_invoice)
        self.set_order_withdraw_done.connect(self.order_manager.set_order_withdraw_done)
        self.set_order_status_withdraw_fail.connect(self.order_manager.set_order_status_withdraw_fail)
        self.del_order.connect(self.order_manager.del_order)

    def interupt(self, a, b):
        sys.exit()

    def start(self):
        self.loop_worker.start()
        
    def load_users_pubkeys(self):
        file = open('users.pubkey', 'r')
        users_list = file.readlines()
        file.close()

        self.users_list = []

        for user in users_list:
            if user[-1] == '\n':
                user = user[:-1]
            self.users_list.append(user)

    def add_user(self, user):
        self.users_list.append(user)
        file = open('users.pubkey', 'a')
        file.write(f"{user}\n")
        file.close()

    def update_filters(self):
        self.load_users_pubkeys()

        # Register to npub notifications
        npub = self.private_key.public_key.hex()
        self.filters = Filters([
            Filter(pubkey_refs=[npub], kinds=[EventKind.TEXT_NOTE, EventKind.ENCRYPTED_DIRECT_MESSAGE]),
            Filter(authors=self.users_list, kinds=[EventKind.SET_METADATA]),

        ])

        self.relay_manager.add_subscription_on_all_relays('rektbot', self.filters)

        request = [ClientMessageType.REQUEST, 'rektbot']
        request.extend(self.filters.to_json_array())
        message = json.dumps(request)
        self.publish_to_all_relays(message)

    def connect_relays(self):
        self.relay_manager = RelayManager()
        log.info("Add relay wss://nostr.oxtr.dev")
        self.relay_manager.add_relay("wss://nostr.oxtr.dev")
        log.info("Add relay wss://nostr.mom")
        self.relay_manager.add_relay("wss://nostr.mom")
        log.info("Add relay wss://relay.damus.io")
        self.relay_manager.add_relay("wss://relay.damus.io")
        log.info("Add relay wss://nostr-relay.lnmarkets.com")
        self.relay_manager.add_relay("wss://nostr-relay.lnmarkets.com")
        time.sleep(2)
        log.info(f"Register for notification on pubkey {self.private_key.public_key.bech32()}")

    def publish_to_all_relays(self, msg):
        log.log(15,f"Publish message to all relays({msg})")
        for relay in self.relay_manager.relays.values():
            if relay.policy.should_write:
                relay.publish(msg)

    def reply_to(self, note_id, user, msg: str, mode: str):
        if note_id:
            log.info(f"Reply to note {note_id[:5]}_{note_id[-5:]} from user {user[:5]}_{user[-5:]}, mode:{mode}")
        else:
            log.info(f"Reply to user {user[:5]}_{user[-5:]}, mode:{mode}")

        msg2 = msg
        msg2.replace('\n', ' ')
        log.log(15,f"Message: {msg2}")

        if mode == 'note':
            reply = Event(content=msg)
            # create 'p' tag reference to the pubkey you're replying to
            reply.add_pubkey_ref(user)
        elif mode == 'dm':
            reply = EncryptedDirectMessage(recipient_pubkey=user, cleartext_content=msg)

        # create 'e' tag reference to the note you're replying to
        if note_id:
            reply.add_event_ref(note_id)

        self.private_key.sign_event(reply)
        self.relay_manager.publish_event(reply)

    def loop(self, *args, **kwargs):
        while True:
            self.listen_notifications()
            self.check_unpaid_orders()
            self.check_open_orders()
            time.sleep(2)

    def listen_notifications(self):
        while self.relay_manager.message_pool.has_events():
            event_msg = self.relay_manager.message_pool.get_event()
            self.handle_event(event_msg.event.to_json()[1])

    def check_unpaid_orders(self):
        unpaid_orders = self.order_manager.list_unpaid_orders()

        for order in unpaid_orders:
            # status = RPC.invoice_status(order.order_id)
            status = self.lnm.get_deposit_status(order.deposit_id)
            if status :
                self.set_order_paid.emit(order.order_id)
            #  TODO: handle expired deposit to lnm (timestamp?)

            # elif status == 'expired':
            #     self.set_order_expired.emit(order.order_id)

    def check_open_orders(self):
        db_open_orders = self.order_manager.list_open_orders()
        lnm_running_orders = self.lnm.get_running_positions()

        #  If fail to fetch running positions
        if type(lnm_running_orders) is not list:
            return
        
        closed_orders = []
        
        for order in db_open_orders:
            # if order closed on LNM side
            if order.lnm_id not in lnm_running_orders:
                closed_orders.append(order)
        
        # if some closed orders
        if closed_orders:
            lnm_closed_orders = self.lnm.get_closed_positions()
            for order in closed_orders:
                order_id = order.order_id
                lnm_id = order.lnm_id
                lnm_order = lnm_closed_orders[lnm_id]
                close_price = lnm_order['exit_price']
                # profit = lnm_order['pl'] - lnm_order['opening_fee'] \
                #          - lnm_order['closing_fee'] - lnm_order['sum_carry_fees']
                data = {
                    'order_id': order_id,
                    'price': close_price,
                }
                self.set_order_close.emit(data)

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
        # TODO: refactor (split) handle_event()

        #if event type is METADATA (used for get LUD16 lnurl)
        if event['kind'] == EventKind.SET_METADATA:
            pubkey = event['pubkey']
            content = json.loads(event['content'])
            # if contain lnurl for user
            if 'lud16' in content.keys():
                self.lnurl_list[pubkey] = content['lud16']
                log.log(15,f"Update lud16 for {pubkey=}: {content['lud16']}")

        # if new event
        elif not self.in_history(event['id']):
            log.info(f"Get notification")
            log.log(15, f"Event:{event}")

            note_id = event['id']
            note_from = event['pubkey']

            if note_from not in self.users_list:
                self.add_user(note_from)
                self.update_filters()

            note_content = event['content']
            if event['kind'] == EventKind.TEXT_NOTE:
                note_type = 'note'
            elif event['kind'] == EventKind.ENCRYPTED_DIRECT_MESSAGE:
                note_type = 'dm'
                note_content = self.private_key.decrypt_message(note_content, event['pubkey'])
                log.log(15, f"Decrypted message = {note_content}")
            else:
                return

            note_content = note_content.lower()

            #  If long or short order
            if ('long ' in note_content) or ('short ' in note_content):
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
                    leverage = 100
                else:
                    leverage = int(leverage[0])
                log.log(15,f"{leverage=}")
                
                tp = re.findall(pattern_tp, note_content)
                
                #  Open order
                log.log(15, f"{amount=}, {tp=}")
                if amount:

                    amount = int(amount[0])

                    trade_amount_dollar, _, _ = self.lnm.estimate_dollar_value(amount, leverage)
                    log.log(15, f"{type(trade_amount_dollar)=}, {trade_amount_dollar}")
                    if trade_amount_dollar < 1.0:
                        msg = f"Position value < 1$ ({trade_amount_dollar}$), increase margin or leverage!"
                        self.reply_to(note_id, note_from, msg, note_type)
                        return

                    # # min amount
                    # if amount < 100:
                    #     amount = 100
                    # max amount
                    if amount > 2000:
                        amount = 2000

                    if tp:
                        tp = int(tp[0])
                    else:
                        tp = 0

                    log.log(15,f"{order_type=}, {amount=}, {leverage=}, {tp=}")
                    log.info(f'[{note_id[:5]}_{note_id[-5:]}] {note_from[:5]}_{note_from[-5:]} request for LONG {amount} sats')
                    self.new_order.emit({'order_id': note_id,
                                         'user': note_from,
                                         'amount': amount,
                                         'order_type': order_type,
                                         'tp': tp,
                                         'leverage': leverage,
                                         'mode': note_type,
                                         })

            #  Withdraw by lnurl requested
            elif ('lnurl' in note_content) and (note_type == 'dm'):

                data = {
                    'user': note_from,
                    'withdraw_mode': 'lnurl',
                    }
                self.set_order_withdraw_requested.emit(data)

            elif ('invoice' in note_content) and (note_type == 'dm'):

                data = {
                    'user': note_from,
                    'withdraw_mode': 'invoice',
                }
                self.set_order_withdraw_requested.emit(data)

            elif ('lnbc' in note_content) and (note_type == 'dm'):
                pattern = r'lnbc\S+'
                invoice = re.findall(pattern, note_content)[0]

                data = {
                    'user': note_from,
                    'invoice': invoice,
                }
                self.set_order_withdraw_receive_invoice.emit(data)

    def on_new_order(self, order):
        # invoice = RPC.invoice(order.amount, order.order_id)
        invoice, hash = self.lnm.deposit_invoice(order.amount,)
        log.info('Generate invoice')
        log.log(15,f'invoice: {invoice}')
        self.set_order_unpaid.emit({'order_id': order.order_id, 'invoice': invoice, 'hash': hash})
        
    def on_unpaid(self, order):
        self.reply_to(order.order_id, order.user, order.invoice, order.mode)
    
    def on_paid(self, order):
        log.info(f"Received payment for invoice {order.order_id[:5]}_{order.order_id[-5:]}")
        self.reply_to(order.order_id, order.user, f"I receive your {order.amount} sats, you'll be rekt soon!", order.mode)
        self.set_order_funding.emit(order.order_id)
        # TODO: delete invoice on CLN side and log it
    
    def on_expired(self, order):
        # TODO: Delete invoice on DB and CLN
        pass
    
    def on_funding(self, order):
        # self.detach_send_funds_to_lnm(order)
        pass
    
    def on_funded(self, order):
        log.info(f'Funding success for invoice {order.order_id[:5]}_{order.order_id[-5:]}')
        log.log(15, f"on_funded({order=})")
        # TODO: Log it in separate records
        # TODO: handle if position fail to open
        price = self.lnm.get_price()

        tp = order.tp

        # if TP < minimum gap
        if order.order_type == 'long':
            if tp < price + 100:
                tp = 0
        elif order.order_type == 'short':
            if tp > price - 100:
                tp = 0

        # If no tp selected
        if tp < 1:
            # tp = None
            delta = random.randint(50, 300)/10000

            if order.order_type == 'long':
                tp = round((1 + delta) * price)
            else:
                tp = round((1 - delta) * price)
            order.tp = tp
            order.save()
            log.log(15, f"Random TP set at {tp} ({delta=})")

        if order.order_type == 'long':
            if tp < price + 100:
                tp = None
        elif order.order_type == 'short':
            if tp > price - 100:
                tp = None

        # if tp and (order.tp != tp):
        #     if order.order_type == 'long':
        #         self.reply_to(order.order_id, order.user, "TP too close, disabled, you'll hodl or be rekt!", order.mode)
        #     else:
        #         self.reply_to(order.order_id, order.user, "TP too close, disabled, you'll be hedged or rekt!", order.mode)

        position = self.lnm.open_market_position(order.order_type, order.amount, order.leverage, tp)
        if not position:
            log.info("Open position fail!")
            return
        open_price = position['price']
        lnm_id = position['id']
        trade_amount = position['trade_amount']
        margin = position['margin']
        fee = position['fee']
        params = {'order_id': order.order_id,
                  'price': open_price,
                  'lnm_id': lnm_id,
                  'trade_amount': trade_amount,
                  'margin': margin,
                  'fee': fee,
                  }
        self.set_order_open.emit(params)

    def on_funding_fail(self, order):
        log.info(f'Funding fail for invoice {order.order_id[:5]}_{order.order_id[-5:]}')
        #  TODO: implement refund
        #  TODO: notify admin

    def on_open(self, order):
        log.info(f'Trade open at {order.open_price} for order {order.order_id[:5]}_{order.order_id[-5:]}, TP={order.tp}')
        if order.order_type == 'long':
            side = 'LONG'
        else:
            side = 'SHORT'
        msg = f'{side} open at {order.open_price}, TP={order.tp}'
        self.reply_to(order.order_id, order.user, msg, order.mode)
    
    def on_close(self, order):
        msg = f'Trade close at {order.close_price} for order {order.order_id[:5]}_{order.order_id[-5:]}'

        log.info(msg)
        msg = f'Trade closed at {order.close_price}\n'
        if order.profit > 0:
            msg += f'Congrats, you earn {order.profit}sats!'
        else:
            msg += f'booooooo you get rekt of {abs(order.profit)} sats!'
        msg += f'\n You can now withdraw your fund, just send "lnurl" or "invoice" by DM!'
        self.reply_to(order.order_id, order.user, msg, order.mode)
        # TODO: cleanup db and log history?

    def detach_withdraw(self, data):
        log.log(15, f"detach_withdraw({data=})")
        amount = data["total_amount"]
        invoice = data['invoice']
        # withdraw directly from LNM
        if amount > 1000:
            function = self.lnm.withdraw
            params = (invoice, amount,)
        # withdraw from our node
        else:
            function = RPC.pay_invoice
            params = (invoice,)

        worker = Worker(function, params)
        worker.data = data
        # append worker to list belonging to self for avoid thread stop by garbage collector
        self.worker_list.append(worker)
        worker.result.connect(self.after_detach_withdraw)
        worker.start()

    def after_detach_withdraw(self, out):
        log.log(15, f"after_detach_withdraw({out=})")
        ret = out['return']
        data = out['data']

        if not ret:
            # switch all orders status back to 'closed'
            batch_list = data['batch_list']
            user = batch_list[0].user
            for order in batch_list:
                order_id = order.order_id
                price = order.close_price
                data = {
                    'order_id': order_id,
                    'price': price,
                }
                self.set_order_status_withdraw_fail.emit(data)
            # Notify user
            msg = 'Cannot process to withdraw, retry later!'
            self.reply_to(None, user, msg, 'dm')
        else:
            self.set_order_withdraw_done.emit(data)

    def on_withdraw_requested(self, data):
        log.log(15, f"on_withdraw_requested({data=})")
        if data['mode'] == 'lnurl':
            user = data['batch_list'][0].user
            if user in self.lnurl_list.keys():
                url = self.lnurl_list[user]
                invoice = LUD16.get_invoice(url, data['total_amount'])
                if not invoice:
                    return
                data['invoice'] = invoice
                # Start withdraw in a new thread, trigger set_order_withdraw_done on withdrawal end
                self.detach_withdraw(data)

            else:
                # Notice user that no public lnurl
                msg = "You don't have a public LUD16 LNURL! add one or withdraw by invoice!"
                self.reply_to(None, user, msg, 'dm')
                return
        # TODO: maybe this path never used?
        if data['mode'] == 'invoice':
            self.detach_withdraw(data)
            # # Notify user to send an invoice
            # user = data['batch_list'][0].user
            # amount = data['total_amount']
            # msg = f"Please send me BOLT11 invoice for amount: {amount}sats"
            # self.reply_to(None, user, msg, 'dm')

    def on_withdraw_notify_amount(self, data):
        log.log(15, f"on_withdraw_notify_amount({data})")
        # Notify user to send an invoice
        if len(data['batch_list']) == 0:
            user = data['user']
        else:
            user = data['batch_list'][0].user
        amount = data['total_amount']
        if 'wrong_amount' in data.keys():
            wrong = True
        else:
            wrong = False

        if not wrong and amount > 0:
            msg = f"Please send me BOLT11 invoice for amount: {amount}sats"
        elif wrong:
            msg = f"Wrong invoice amount, please send me BOLT11 invoice for amount: {amount}sats"
        else:
            return
        self.reply_to(None, user, msg, 'dm')

    def on_withdraw_done(self, data):
        log.log(15,f"on_withdraw_done({data=})")
        user = data['batch_list'][0].user
        msg = f"Successfully withdraw {data['total_amount']}sats!"
        self.reply_to(None, user, msg, 'dm')

    def on_deleted(self, order):
        pass


app = QCoreApplication()
bot = NostrBot(config.key)
bot.loop_worker.start()

app.exec()

sys.exit(0)



