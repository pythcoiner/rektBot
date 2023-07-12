import json
import logging

from lnmarkets import rest
import config

log = logging.getLogger()


class LNMarkets:
    
    def __init__(self, key, secret, passphrase):
        options = {'key': key,
                   'secret': secret,
                   'passphrase': passphrase,
                   'network': 'mainnet'}
        self.client = rest.LNMarketsRest(**options)
        
    def deposit_invoice(self, amount):
        ret = self.client.deposit({'amount': amount, }, format='json')
        
        if ret['paymentRequest']:
            log.info(f"[LNMarkets] API process invoice")
            log.debug(f"[LNMarkets] Invoice: {ret['paymentRequest']}")
            return ret['paymentRequest']
        else:
            log.info(f"[LNMarkets] API fail to make deposit invoice")
            log.debug(f"[LNMarkets] API returns {ret}")
            return None
        
        
lnm = LNMarkets(config.lnmarkets['key'], config.lnmarkets['secret'], config.lnmarkets['passphrase'])

