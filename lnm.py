import json
import logging

from lnmarkets import rest
import config

log = logging.getLogger()
log.setLevel(logging.DEBUG)


options = {'key': config.lnmarkets['key'],
           'secret': config.lnmarkets['secret'],
           'passphrase': config.lnmarkets['passphrase'],
           'network': 'mainnet'}

lnm = rest.LNMarketsRest(**options)

# ret = lnm.futures_new_position({
#     'type': 'm',
#     'side': 'b',
#     'leverage': 1,
#     'quantity': 100,
#   })

# ret = lnm.get_user(format='json')
# print(type(ret))
# print(json.dumps(ret, indent=2))

ret = lnm.deposit({'amount': 10}, format='json')
print(ret)






