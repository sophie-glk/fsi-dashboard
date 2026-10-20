from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://stwno.de/infomax/daten-extern/html/"
URL = BASE + "speiseplan-render.php"

def get_menu(date, location = "UNI-R"):
    response = requests.post(
        URL,
        data={
            "func": "make_spl",
            "locId": location,
            "lang": "de",
            "date": date,
            "w": "",
        },
        headers={"Referer": BASE + f"speiseplaene.php?einrichtung={location}"},
        timeout=15,
    )
    response.raise_for_status()
    html =  response.text


    soup = BeautifulSoup(html, "html.parser")
    foods = {}
    for header in soup.find_all("tr", class_="gruppenkopf"):
        title = header.find("td", class_="gk").get_text(" ", strip=True)
        current_food = []
        for row in header.find_next_siblings("tr"):
            if "gruppenkopf" in row.get("class", []):
                break
            if "essenzeile" in row.get("class", []):
                current_food.append(row)
        foods[title] = current_food 
    parsed_foods = {"mains": [], "sides": [], "deserts": [], "soups": []}
    for title,food_rows in foods.items():
        for food in food_rows:
            display_name = food.find(class_="cell1").get_text(" ", strip=True)
            if not display_name:
                continue
            # remove allergens in brackets from name
            split_string =  display_name.split("(")
            name = split_string[0].strip() 
            allergens = []
            if len(split_string) > 1:
                allergens = split_string[1].rstrip(")").split(",")
            images = food.find_all("img")
            image = ""
            for img in images:
                if img.get("alt"):
                    continue
                else: 
                    image = urljoin(URL, img["src"])
                    break
            price = food.find(class_="preis").get_text(" ", strip=True)
            tooltips = food.find_all(class_="tooltip")
            food_type = ""
            for tip in tooltips:
                text = tip.get_text(" ", strip=True)
                if "Vegan" in text:
                    food_type = "Vegan"
                elif "vegetarisch" in text:
                    food_type = "Vegetarisch" 
            data = {"name": name, "allergens": allergens, "price": price, "type": food_type, "image": image}
            key = "mains"
            if title == "Suppen":
                key = "soups"
            elif title == "Beilagen":
                key = "sides"
            elif title == "Nachspeisen":
                key = "deserts"
            parsed_foods[key].append(data)
    #print(html)
    return parsed_foods
