import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import requests

TW_ACCOUNT_ID = "940ff92e-7e3c-42a4-bbad-9a6fa9eab519"
TW2_ACCOUNT_ID = "b0a06267-2091-4ada-a38d-3243cf9ddc9b"
US_ACCOUNT_ID = "8dab33c4-8ee3-42c3-a088-943367115688"
CRYPTO_ACCOUNT_ID = "ef2494d7-0734-47b2-901e-5625debb912e"

class DataImporter():
    def __init__(self, broker, file):
        if broker not in ["cathay", "ft"]:
            raise Exception("Invalid broker")
        self._broker = broker
        self._stock_map = {}
        if broker == "cathay":
            self._activities = self._parse_cathay_csv(file)
        elif broker == "ft":
            self._activities = self._parse_ft_csv(file)

    def _update_stock_map(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="h4")

        for row in table.find_all('tr')[1:]:  # 跳過表頭
            cols = row.find_all('td')
            if len(cols) >= 4:
                code_name = cols[0].text.strip()
                code, name = code_name.split("\u3000")
                stock_type = cols[3].text.strip()

                if code and code[0].isdigit():  # 確保是股票代碼
                    if stock_type == "上市":
                        self._stock_map[name] = code + ".TW"
                    elif stock_type == "上櫃":
                        self._stock_map[name] = code + ".TWO"

    def _parse_cathay_csv(self, file):
        def get_action(value):
            if value == "現買":
                return "BUY"
            elif value == "現賣":
                return "SELL"
            raise ValueError(f"Unknown value {value}")

        def get_code_by_name(name):
            if not self._stock_map:
                self._update_stock_map("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2")
                self._update_stock_map("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4")

            if name in self._stock_map:
                return self._stock_map[name]
            else:
                raise ValueError(f"Unknown stock name {name}")

        def get_account_id_by_code(code):
            if code in ["2330.TW", "00878.TW", "006208.TW"]:
                return TW_ACCOUNT_ID
            else:
                return TW2_ACCOUNT_ID

        df = pd.read_csv(file, skiprows=1)
        res = []
        for _, row in df.iterrows():
            code = get_code_by_name(row["股名"])
            account_id = get_account_id_by_code(code)
            data = {
                "activities": [
                    {
                        "accountId": account_id,
                        "currency": "TWD",
                        "dataSource": "YAHOO",
                        "date": datetime.strptime(row["日期"], "%Y/%m/%d").isoformat(),
                        "fee": row["手續費"] + int(str(row["交易稅"].replace(",", ""))),
                        "quantity": int(str(row["成交股數"]).replace(",", "")),
                        "symbol": code,
                        "type": get_action(row["買賣別"]),
                        "unitPrice": row["成交價"],
                        "comment": "Imported from importer script"
                    }
                ]
            }
            res.append(data)
        return res

    def _parse_ft_csv(self, file):
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

        df = pd.read_csv(file)
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

    def activities(self):
        return self._activities


if __name__ == "__main__":
    importer = DataImporter("cathay", "cathay.csv")
    print(importer.activities())
