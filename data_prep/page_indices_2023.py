"""
0-based page indices for the council remuneration page in each 2023 SOFI report.
Municipalities with no 2023 report or no readable PDF are excluded.
"""

PAGE_INDICES_2023 = {
    "Abbotsford":                14,
    "Armstrong":                 26,
    "Burnaby":                   39,   # override
    "Campbell River":            None, # image PDF - uses manual_remuneration_2023.csv
    "Central Saanich":           35,
    "Chilliwack":                25,
    "Coldstream":                65,   # override
    "Colwood":                    8,
    "Comox":                     None, # image PDF - uses manual_remuneration_2023.csv
    "Coquitlam":                 50,
    "Courtenay":                 30,
    "Cranbrook":                  3,
    "Dawson Creek":              37,
    "Delta":                     31,
    "Esquimalt":                 None, # image PDF - uses manual_remuneration_2023.csv
    "Fort St. John":              3,   # override
    "Kamloops":                   4,   # override
    "Kelowna":                    1,
    "Lake Country":               3,
    "Langford":                   5,
    "Langley (City)":            33,
    "Langley (District)":         3,
    "Maple Ridge":               40,   # override
    "Mission":                   None, # image PDF - uses manual_remuneration_2023.csv
    "Nanaimo":                    4,   # override
    "Nelson":                    35,
    "New Westminster":           40,   # override
    "North Cowichan":             5,   # override
    "North Saanich":             None, # wrong page - uses manual_remuneration_2023.csv
    "North Vancouver (City)":    33,   # override
    "North Vancouver (District)": 35,
    "Oak Bay":                   35,
    "Parksville":                 3,
    "Penticton":                 None, # image PDF - uses manual_remuneration_2023.csv
    "Pitt Meadows":              None, # image PDF - uses manual_remuneration_2023.csv
    "Port Alberni":              33,
    "Port Coquitlam":            32,
    "Port Moody":                 7,
    "Powell River":              59,   # override
    "Prince George":             19,
    "Prince Rupert":              4,
    "Quesnel":                    4,
    "Richmond":                  None, # image PDF - uses manual_remuneration_2023.csv
    "Saanich":                   40,
    "Salmon Arm":                40,
    "Sechelt":                   None, # image PDF - uses manual_remuneration_2023.csv
    "Sidney":                    39,
    "Sooke":                     None, # wrong page - uses manual_remuneration_2023.csv
    "Squamish":                  None, # image PDF - uses manual_remuneration_2023.csv
    "Summerland":                 4,
    "Surrey":                    None, # wrong page - uses manual_remuneration_2023.csv
    "Terrace":                   None, # image PDF - uses manual_remuneration_2023.csv
    "Vancouver":                 75,   # override
    "Victoria":                  49,   # override
    "View Royal":                None, # image PDF - uses manual_remuneration_2023.csv
    "West Kelowna":               5,
    "West Vancouver":            40,   # override
    "Whistler":                  45,
    "White Rock":                41,
    "Williams Lake":             27,   # override
}
