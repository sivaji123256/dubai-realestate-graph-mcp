"""
Verified official contact info for developers identified by
ingestion/tag_developers.py. Checked against each company's live website,
not guessed. Deliberately small and static -- extend only with verified
info, never fabricate a contact.
"""

DEVELOPER_CONTACTS = {
    "DAMAC": {
        "contact_url": "https://www.damacproperties.com/en/contact-us/",
        "email": "connect@damacgroup.com",
    },
    "Emaar": {
        "contact_url": "https://www.emaar.com/en/contact-us/",
        "phone": "800 36227 (UAE)",
        "email": "Sales_Enquiry@emaar.ae",
    },
    "Binghatti": {
        "contact_url": "https://www.binghatti.com/en/contact-us",
    },
    "Sobha": {
        "contact_url": "https://sobharealty.com/contact-us",
    },
    "Azizi": {
        "contact_url": "https://www.azizidevelopments.com/contact-us",
        "phone": "+971 4 359 6673",
        "email": "info@azizidevelopments.com",
    },
    "Danube": {
        "contact_url": "https://danubeproperties.com/contact-us/",
        "phone": "+971 800 5757",
    },
    "Samana": {
        "contact_url": "https://www.samanadevelopers.com/contact",
    },
}


def get_developer_contact(developer_name: str):
    if not developer_name:
        return None
    for name, contact in DEVELOPER_CONTACTS.items():
        if name.lower() == developer_name.lower():
            return {"developer": name, **contact}
    return {"developer": developer_name, "note": "Developer identified, but verified contact details aren't in our directory yet."}
