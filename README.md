# Edge Scanner

**Arbitrage • Middles • +EV**

Open-source sports betting scanner that finds arbitrage opportunities, middle bets, and +EV plays across US and EU bookmakers.

## Features

| Tab | What it finds | Risk profile |
|-----|---------------|--------------|
| **Arbitrage** | Guaranteed profit by betting both sides across different books | Zero risk |
| **Middles** | Line gaps where both bets can win if the result lands in between | High variance, +EV over time |
| **+EV** | Soft book odds better than sharp book fair value | Medium variance, profit over volume |

## How It Works

The scanner pulls odds from The Odds API across multiple regions (US, EU, UK, AU) and:

1. **Arbitrage** — finds where the sum of inverse odds across books is less than 1, guaranteeing profit regardless of outcome
2. **Middles** — finds where books disagree on spreads/totals, creating a gap where both sides can win
3. **+EV** — compares soft book odds to sharp reference (Pinnacle), identifying bets with positive expected value

## Setup

1. Clone this repo
2. Install dependencies: `pip install -r requirements.txt`
3. Get a free API key from [The Odds API](https://the-odds-api.com/)
4. Run: `python app.py`

Your browser opens automatically. Enter your API key and scan.

**Optional:** Create a `.env` file with your API key to skip manual entry:
```
ODDS_API_KEY=your_api_key_here
```

For automatic key rotation, copy `api_keys.example.json` to `data/api_keys.json` and add your keys there. The `data/` directory is ignored by git, so the live key roster stays local. When a key runs out of monthly usage credits, the scanner marks it exhausted, retries with the next enabled key, and reactivates exhausted keys after the configured monthly reset.

## Markets Scanned

| Sport | Markets |
|-------|---------|
| NFL, NBA, MLB, NHL | Moneyline, Spreads, Totals |
| Soccer (EPL, La Liga, etc.) | Spreads, Totals only* |

*Soccer moneyline is three-way (win/draw/lose) — excluded from two-way scanning.

## API Usage

Each scan uses one API call per sport. Free tier: 500 requests/month.

Default sports use ~6-10 calls per scan depending on what's in season.

## Understanding the Results

### Arbitrage

ROI = guaranteed return on total stake. A 2% ROI means $2 profit on $100 staked.

Stakes are split so you get the same payout regardless of outcome.

### Middles

EV = expected value based on historical probability of landing in the gap.

NFL key numbers (3, 7) significantly boost probability for spread middles — these margins occur more often due to field goals and touchdowns.

Middles lose small amounts most of the time and win big occasionally — positive EV over many bets, but high variance on any single bet.

### +EV

Edge = how much better the soft book odds are compared to sharp book fair value.

Sharp books (Pinnacle) have tight lines with minimal vig (~2%). When soft books offer better odds than the sharp-implied fair price, that's a +EV bet.

Kelly staking helps size bets based on edge — quarter Kelly recommended to reduce variance.

## Configuration

Configurable via the UI:
- Regions (US, US2, UK, EU, AU)
- Sports selection
- Exchange commission rate (for Betfair, etc.)
- Minimum gap for middles
- Minimum edge for +EV
- Sharp reference book (Pinnacle, Betfair, Matchbook)
- Kelly fraction (full, half, quarter, tenth)
- Stake amount / bankroll

## Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Data:** The Odds API

## License

MIT

## Contributing

PRs welcome. Ideas for future versions:
- Alerts/notifications
- Historical tracking
- Three-way arbitrage (soccer moneylines)
- Player props

