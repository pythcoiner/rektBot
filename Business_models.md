## Trading challenge bot
- Daily/Weekly/Monthly Challenge?
- User open position w/ margin + TP (fixed leverage?)
- Max amount for each trade?
- For each trade initiated w/ the bot:
  - margin = amount - trading fee (commission take by bot?)
  - margin split (a%/b%) a% go to trading margin, b% to pot
- At the end of challenge period:
  - Close all open trades
  - Sort users by best trade profit (sats)
  - nets profits are summedand split (c%/d%) and c% to winner/ d% to bot
  - pot is split (e%/f%/g%) e% to winner, f% to reserve, g% to bot
- Withdraw: 0.5% fee w/ 100sats mini (LNM policy)
- [Cool feature] max 50 trades => if len(trades) > 49:
  - lower `free` margin trade is closed (funds are lost for user)
  - lost funds add to pot


## Crash challenge
- close all position at crash
- last user to successfully deposit funds get all the funds

## Stablesats bot

## LNP2P/Nostr
