"""Versioned, reviewed public sources for the account-security corpus."""

TOPIC = "Account security: passwords, MFA, phishing and federated sign-in"
RIGHTS_URL = "https://www.nist.gov/copyrights-disclaimers"
RIGHTS = (
    "NIST public information: copying/distribution permitted except material "
    "marked copyrighted; source attribution retained. Article images excluded."
)

LEGAL_SOURCES = [
    {
        "id": "nist-sp800-63-4",
        "filename": "nist_sp_800_63_4.pdf",
        "title": "NIST SP 800-63-4: Digital Identity Guidelines",
        "url": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63-4.pdf",
        "source_page": "https://csrc.nist.gov/pubs/sp/800/63/4/final",
    },
    {
        "id": "nist-sp800-63b-4",
        "filename": "nist_sp_800_63b_4.pdf",
        "title": "NIST SP 800-63B-4: Authentication and Authenticator Management",
        "url": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63b-4.pdf",
        "source_page": "https://csrc.nist.gov/pubs/sp/800/63/b/4/final",
    },
    {
        "id": "nist-sp800-63c-4",
        "filename": "nist_sp_800_63c_4.pdf",
        "title": "NIST SP 800-63C-4: Federation and Assertions",
        "url": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63c-4.pdf",
        "source_page": "https://csrc.nist.gov/pubs/sp/800/63/c/4/final",
    },
]

ARTICLE_SOURCES = [
    ("nist_good_password", "https://www.nist.gov/cybersecurity-and-privacy/how-do-i-create-good-password"),
    ("nist_mfa", "https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/multi-factor-authentication"),
    ("nist_phishing", "https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/phishing"),
    ("nist_phishing_resistance", "https://www.nist.gov/blogs/cybersecurity-insights/phishing-resistance-protecting-keys-your-kingdom"),
    ("nist_identity_revision4", "https://www.nist.gov/blogs/cybersecurity-insights/lets-get-digital-updated-digital-identity-guidelines-are-here"),
]
