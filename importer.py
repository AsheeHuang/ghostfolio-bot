# write a python binary file importer that reads a csv file then parse it and send curl api to a server
# the server api is a POST request that accepts the following json format:
"""
{
    "activities": [
        {
            "currency": "USD",
            "dataSource": "YAHOO",
            "date": "2021-09-15T00:00:00.000Z",
            "fee": 19,
            "quantity": 5,
            "symbol": "MSFT",
            "type": "BUY",
            "unitPrice": 298.58
        }
    ]
}
"""

from datetime import datetime
import argparse
import requests
import json
import sys
import os
import pandas as pd

TARGET_IP = "192.168.1.50"
PORT = "3333"

# TODO: get account id by calling /api/v1/accounts
TW_ACCOUNT_ID = "940ff92e-7e3c-42a4-bbad-9a6fa9eab519"
US_ACCOUNT_ID = "8dab33c4-8ee3-42c3-a088-943367115688"
CRYPTO_ACCOUNT_ID = "ef2494d7-0734-47b2-901e-5625debb912e"

STOCK_MAP = {
    "富邦台50": "006208.TW",
    "國泰永續高股息": "00878.TW",
    "元大高股息": "0056.TW",
    "智原": "3035.TW",
    "力致": "3483.TW"
}

POST_URL = f"http://{TARGET_IP}:{PORT}/api/v1"
IMPORT_URL = f"{POST_URL}/import"
AUTH_URL = f"{POST_URL}/auth/anonymous"

def parse_cathy_csv(args):
    def get_action(value):
        if value == "現買":
            return "BUY"
        elif value == "現賣":
            return "SELL"

        raise ValueError(f"Unknown value {value}")

    df = pd.read_csv(args.file)
    res = []
    for _, row in df.iterrows():
        if row["股名"] not in STOCK_MAP:
            print(f"Unknown stock name {row['股名']}")
            raise ValueError(f"Unknown stock name {row['股名']}")

        data = {
            "activities": [
                {
                    "accountId": TW_ACCOUNT_ID,
                    "currency": "TWD",
                    "dataSource": "YAHOO",
                    "date": datetime.strptime(row["日期"], "%Y/%m/%d").isoformat(),
                    "fee": row["手續費"] + row["交易稅"],
                    "quantity": int(str(row["成交股數"]).replace(",", "")),
                    "symbol": STOCK_MAP[row["股名"]],
                    "type": get_action(row["買賣別"]),
                    "unitPrice": row["成交價"],
                    "comment": "Imported from importer script"
                }
            ]
        }
        res.append(data)
    return res

def parse_ft_csv(args):
    def get_action(value):
        action_map = {
            "BUY": "BUY",
            "SELL": "SELL",
            "Dividend": "DIVIDEND",
            "Interest": "INTEREST",
            "Other": "SKIP"
        }
        if value not in action_map:
            raise ValueError(f"Unknown value {value}")
        return action_map[value]

    df = pd.read_csv(args.file)
    res = []
    for _, row in df.iterrows():
        action = get_action(row["Action"])
        data = {
            "activities": [
                {
                    "accountId": US_ACCOUNT_ID,
                    "currency": "USD",
                    "dataSource": "YAHOO",
                    "date": datetime.strptime(row["TradeDate"], "%Y-%m-%d").isoformat(),
                    "symbol": row["Symbol"].split(" ")[0],
                    "fee": row["Fee"],
                    "type": action,
                    "comment": "Imported from importer script"
                }
            ]
        }
        extra_data = {}
        if action == "DIVIDEND":
            extra_data["quantity"] = 1
            extra_data["unitPrice"] = row["Amount"]
        elif action == "INTEREST":
            extra_data["symbol"] = "Interest"
            extra_data["dataSource"] = "MANUAL"
            extra_data["quantity"] = 1
            extra_data["unitPrice"] = row["Amount"]
        elif action == "BUY" or action == "SELL":
            extra_data["quantity"] = abs(row["Quantity"])
            extra_data["unitPrice"] = row["Price"]
        elif action == "SKIP":
            continue

        data["activities"][0].update(extra_data)
        res.append(data)
    return res

def send_curl_api(args, activities):
    SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")
    if not SECURITY_TOKEN:
        print("Please set SECURITY_TOKEN environment variable")
        sys.exit(1)

    resp = requests.post(f"{AUTH_URL}", data={"accessToken": SECURITY_TOKEN}, timeout=5)
    if resp.status_code != 201:
        print(f"Failed to authenticate {resp.json()}")
        return

    bearer_token = resp.json()["authToken"]
    headers = {
        "Authorization": f"Bearer {bearer_token}"
    }

    for data in activities:
        print(f"Sending data {json.dumps(data, indent=2)} to {IMPORT_URL}...")
        if not args.y:
            key = input("Do you want to import? (y/n): ")
            if key == "y":
                pass
            elif key == "n":
                continue
            else:
                print("Aborted")
                return

        response = requests.post(IMPORT_URL, json=data, headers=headers, timeout=5)
        if response.status_code != 201:
            print(f"Failed to send import api {response}")
            return
        print("Import successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import a csv file and send curl api to a server")
    parser.add_argument("-f", "--file", help="The csv file to be imported")
    parser.add_argument("--format", help="The format of the csv file", default="cathy", choices=["cathy", "ft"])
    parser.add_argument("-y", help="Import without asking for confirmation", action="store_true")
    args = parser.parse_args()

    if not args.file:
        parser.print_help()
        sys.exit(1)

    print(f"Importing file {args.file} to {TARGET_IP}:{PORT}...)")
    if args.format == "cathy":
        activities = parse_cathy_csv(args)
    elif args.format == "ft":
        activities = parse_ft_csv(args)

    send_curl_api(args, activities)
