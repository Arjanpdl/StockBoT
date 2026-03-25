# Stock Signal Engine Pro V6 Merged

Professional approach used here:
- news as a filter
- volume as a confirmation
- trend as the main decision maker
- risk rules as the boss

What this build adds:
- SPY + QQQ regime filter
- volume surge confirmation
- negative-news BUY blocker
- positive-news context on BUY alerts
- separate Telegram news alerts
- partial profit and trailing-style exits
- max daily loss cutoff
- max trades/day
- quiet heartbeat option
- CSV trade journal

Run:
pip install -r requirements.txt
copy .env.example .env
python -m app.main

Honest recommendation:
Use paper first. This is safer and more selective, but still not guaranteed profitable.
