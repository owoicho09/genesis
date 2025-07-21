# Zoho configuration 1
zoho_email_1 = os.getenv("zoho_email_1")
zoho_app_password_1 = os.getenv("zoho_app_password_1")
if zoho_email_1 and zoho_app_password_1:
    configs.append(SMTPConfig(
        provider="zoho",
        host="smtp.zoho.com",
        port=587,
        use_tls=True,
        username=zoho_email_1,
        password=zoho_app_password_1
    ))

# Zoho configuration 2 - FIXED: Now checking correct variables
zoho_email_2 = os.getenv("zoho_email_2")
zoho_app_password_2 = os.getenv("zoho_app_password_2")
if zoho_email_2 and zoho_app_password_2:
    configs.append(SMTPConfig(
        provider="zoho",
        host="smtp.zoho.com",
        port=587,
        use_tls=True,
        username=zoho_email_2,
        password=zoho_app_password_2
    ))

# Zoho configuration 3 - FIXED: Now checking correct variables
zoho_email_3 = os.getenv("zoho_email_3")
zoho_app_password_3 = os.getenv("zoho_app_password_3")
if zoho_email_3 and zoho_app_password_3:
    configs.append(SMTPConfig(
        provider="zoho",
        host="smtp.zoho.com",
        port=587,
        use_tls=True,
        username=zoho_email_3,
        password=zoho_app_password_3
    ))

# Zoho configuration 4 - FIXED: Now checking correct variables
zoho_email_4 = os.getenv("zoho_email_4")
zoho_app_password_4 = os.getenv("zoho_app_password_4")
if zoho_email_4 and zoho_app_password_4:
    configs.append(SMTPConfig(
        provider="zoho",
        host="smtp.zoho.com",
        port=587,
        use_tls=True,
        username=zoho_email_4,
        password=zoho_app_password_4
    ))
