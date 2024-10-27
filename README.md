### How to start

```
cd ghostfolio-bot
docker build -t ghostfolio_bot .
docker run -v $(pwd):/app --network host ghostfolio_bot:latest
```
