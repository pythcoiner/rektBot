import json
import logging
import math

import bolt11
from lnmarkets import rest
import config

log = logging.getLogger()


class LNMarkets:
    
    def __init__(self, key, secret, passphrase, fee=0.002):
        options = {'key': key,
                   'secret': secret,
                   'passphrase': passphrase,
                   'network': 'mainnet'}
        self.client = rest.LNMarketsRest(**options)
        self.last_running_position = []
        self.fee = fee
        
    def deposit_invoice(self, amount):
        ret = self.client.deposit({'amount': amount, }, format='json')
        
        if 'paymentRequest' in ret.keys():
            log.info(f"[LNMarkets] API process invoice")
            log.log(15,f"[LNMarkets] Invoice: {ret['paymentRequest']}")
            invoice = ret['paymentRequest']
            decoded_invoice = bolt11.decode(invoice)
            payment_hash = decoded_invoice.payment_hash
            return invoice, payment_hash
        else:
            log.info(f"[LNMarkets] API fail to make deposit invoice")
            log.log(15,f"[LNMarkets] API returns {ret}")
            return None

    def deposit_history(self):
        return self.client.deposit_history({}, format='json')

    def get_deposit_status(self, hash):
        history = self.deposit_history()
        if type(history) is not list:
            return
        for i in history:
            if type(i) is not dict:
                return
            elif 'payment_hash' in i.keys():
                if i['payment_hash'] == hash:
                    return i['success']

        return

    def open_long(self, margin, leverage):
        return self.open_market_position('long', margin, leverage)
        
    def open_short(self, margin, leverage):
        return self.open_market_position('short', margin, leverage)

    def open_market_position(self, side, margin, leverage=100, tp=None):
        # TODO: Handle TP + SL
        log.log(15, f"open_market_position({side=}, {margin=}, {leverage=}, {tp=})")
        if side == 'long':
            side = 'b'
        elif side == 'short':
            side = 's'
        else:
            return

        fee = math.ceil(margin * leverage * self.fee)
        margin = margin - fee
        trade_amount = math.floor(margin * leverage)

        params = {
            'type': 'm',
            'side': side,
            'leverage': leverage,
            'margin': margin,  # sats
            # 'quantity': 1, #dollar
        }
        if tp:
            params['takeprofit'] = tp

        ret = self.client.futures_new_position(params, format='json')
        log.log(15, f"LNM open position answer: {ret}")
        if 'code' in ret.keys():
            return

        if ('id' not in ret.keys()) or ('price' not in ret.keys()):
            return

        out = {
            'id': ret['id'],
            'price': ret['price'],
            'trade_amount': trade_amount,
            'margin': margin,
        }
        return out

    def get_running_positions(self):
        positions = []
        ret = self.client.futures_get_positions({'type': 'running'}, format='json')
        if type(ret) is list:
            if len(ret) != len(self.last_running_position):
                self.last_running_position = ret
                log.log(15, f"LNM running position update: {ret}")
            for i in ret:
                positions.append(i['id'])
        else:
            return None

        return positions

    def get_closed_positions(self):
        positions = {}
        ret = self.client.futures_get_positions({'type': 'closed'}, format='json')
        for i in ret:
            positions[i['id']] = i

        return positions

    def get_price(self):
        return float(self.client.futures_get_ticker(format='json')['lastPrice'])

    def get_free_balance(self):
        ret = self.client.get_user(format='json')
        if 'balance' in ret.keys():
            return int(ret['balance'])
        return

    def get_max_withdraw_amount(self):
        balance = self.get_free_balance()
        fee = max(math.ceil(balance * 0.005), 100)
        max_amount = balance - fee
        min_amount = 1000
        if max_amount < min_amount:
            return
        else:
            return max_amount

    def withdraw(self, invoice, amount):
        log.log(15, f"[LNM]withdraw({invoice=}, {amount=})")
        ret = self.client.withdraw({
                        'amount': amount,
                        'invoice': invoice
                      }, format='json')
        log.log(15, f"[LNM] answer: {ret}")

        if type(ret) is not dict:
            return False
        elif 'paymentHash' in ret.keys():
            return True
        else:
            return False

