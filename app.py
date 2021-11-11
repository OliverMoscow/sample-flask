from didkit import generateEd25519Key
from workos import client as workos_client
from flask import Flask, jsonify, render_template, request, redirect
from issue_credential import issueCredential
import json
import errno
import didkit
import stripe
import os
import sys
import smtplib
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

load_dotenv()


app = Flask(__name__)

stripe_keys = {
    "secret_key": os.environ["STRIPE_SECRET_KEY"],
    "publishable_key": os.environ["STRIPE_PUBLISHABLE_KEY"],
}

stripe_prices = {
    "subscription": os.environ["SUBSCRIPTION_PRICE_ID"],
}
gmail_login = {
    "email": os.environ["GMAIL_EMAIL"],
    "password": os.environ["GMAIL_PASSWORD"]
}

# print(stripe.Plan.list(limit=3))
#
stripe.api_key = stripe_keys["secret_key"]


@app.route("/")
def index():
    domain = request.url_root.split(
        "https://")[-1].split("http://")[-1].replace("/", "")
    return render_template("index.html", domain=domain, didkit_version=didkit.getVersion())


@app.route("/success")
def success():
    credential = json.dumps(issueCredential(request), indent=2, sort_keys=True)

    # workos magic link w/ flask email
    # email = credential.credentialSubject["@context"][0].email
    print(credential, file=sys.stderr)
    credential = json.loads(credential)
    email = credential['credentialSubject']['email']   
    print(email, file=sys.stderr)
    session = workos_client.passwordless.create_session(
        {'email': email, 'type': 'MagicLink'}
    )

    # Send a custom email using your own service
    sendEmail(session['link'], email)
    # gmail_user = gmail_login["email"]
    # gmail_password = gmail_login["password"]

    # FROM = gmail_user
    # TO = [email]
    # SUBJECT = "HEI of ONE login link"
    # TEXT = session['link']
    # message = """\
    # From: %s
    # To: %s
    # Subject: %s

    # %s
    # """ % (FROM, ", ".join(TO), SUBJECT, TEXT)

    # try:
    #     server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    #     server.ehlo()
    #     server.login(gmail_user, gmail_password)

    #     print("Email logged in")
    # except:
    #     print('Something went wrong...')

    # try:
    #     server.sendmail(FROM, TO, message)
    #     server.close()

    #     print("Email sent!")
    # except:
    #     print('Something went wrong...')

    return render_template('credential.html', credential=credential, didkit_version=didkit.getVersion())


@app.route("/cancelation")
def cancelation():
    return 'Canceled'


@app.route("/config")
def get_publishable_key():
    stripe_config = {"publicKey": stripe_keys["publishable_key"]}
    return jsonify(stripe_config)


@app.route("/create-checkout-session")
def create_checkout_session():
    domain_url = request.url_root
    stripe.api_key = stripe_keys["secret_key"]
    subscription = stripe.Price.retrieve(stripe_prices["subscription"])

    try:
        # Create new Checkout Session for the order
        # Other optional params include:
        # [billing_address_collection] - to display billing address details on the page
        # [customer] - if you have an existing Stripe Customer ID
        # [payment_intent_data] - capture the payment later
        # [customer_email] - prefill the email input in the form
        # For full details see https://stripe.com/docs/api/checkout/sessions/create

        # ?session_id={CHECKOUT_SESSION_ID} means the redirect will have the session ID set as a query param
        checkout_session = stripe.checkout.Session.create(
            success_url=domain_url +
            "success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=domain_url + "cancelled",
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "name": subscription["nickname"],
                    "quantity": subscription["recurring"]["interval_count"],
                    "currency": subscription["currency"],
                    "amount": subscription["unit_amount"],
                }
            ]
        )
        return jsonify({"sessionId": checkout_session["id"]})
    except Exception as e:
        return jsonify(error=str(e)), 403


# workos magic link auth
@app.route('/callback')
def callback():
    code = request.args.get('code')
    print(code)
    profile_and_token = workos_client.sso.get_profile_and_token(code)

    # Use the information in `profile` for further business logic.
    profile = profile_and_token.profile
    print(profile)
    return jsonify({"status": "success", "user": profile})


if __name__ == 'app':
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        file_handle = os.open('key.jwk', flags)
    except OSError as e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise
    else:
        with os.fdopen(file_handle, 'w') as file_obj:
            file_obj.write(generateEd25519Key())

def sendEmail(body,address):
    mail_content = body
    #The mail addresses and password
    sender_address = gmail_login["email"]
    sender_pass = gmail_login["password"]
    receiver_address = address
    #Setup the MIME
    message = MIMEMultipart()
    message['From'] = sender_address
    message['To'] = receiver_address
    message['Subject'] = 'HEI of ONE login link'   #The subject line
    #The body and the attachments for the mail
    message.attach(MIMEText(mail_content, 'plain'))
    #Create SMTP session for sending the mail
    session = smtplib.SMTP('smtp.gmail.com', 587) #use gmail with port
    session.starttls() #enable security
    session.login(sender_address, sender_pass) #login with mail_id and password
    text = message.as_string()
    session.sendmail(sender_address, receiver_address, text)
    session.quit()
    print('Mail Sent')