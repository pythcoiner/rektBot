# RektBot
rektBot is just a nostr bot to be rekt while trading on LNMarkets.com

you can find him at `npub15w8szlfuwx86zt62q73mkude9gtsm8rzzjshlj3ug8wf6wprvhcsj2nuj0`

## Open a Trade:
just tag the bot with this command in a note:
```
@rektBot long 100
```
this will ask you to fund your account with a LN invoice of 100sats, then open a `LONG` trade

you can also send it command in DM, in this case no need tag it:
```
short 250
```

## Take Profit
You can specify a TP while starting a trade:
```
long 100 tp35000
```
If no TP specified, the bot will decided for you (dont forget you'll be rekt)

## Leverage
Default leverage set at `100` (maximum allowed by LNMarkets.com), but you can customize it:
```
short 250 tp9000 x50
```
(note that the minimum position value on LNMarkets.com is `1$`)

(yes position value used the hegemonist shitcoin ($))

## Withdrawal
- After one (or several) trades is closed (if you don't have been rekt!), you can cashout trough LUD16 lnurl (specified in your nostr profile) or via LN invoice.
- There is no minimum amount for withdraw (LNMarkets have a 1000 sats withdrawal)


