### How to start

```
docker build -t ghostfolio_bot .
docker run -v $(pwd):/app -e BOT_TOKEN={BOT_TOKEN} -e GHOSTFOLIO_TOKEN={GHOSTFOLIO_TOKEN} --network host ghostfolio_bot:latest
```