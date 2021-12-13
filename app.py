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
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText

load_dotenv()


app = Flask(__name__)

stripe_keys = {
    "secret_key": os.environ["STRIPE_SECRET_KEY"],
    "publishable_key": os.environ["STRIPE_PUBLISHABLE_KEY"],
}

stripe_prices = {
    "subscription": os.environ["SUBSCRIPTION_PRICE_ID"],
}

# print(stripe.Plan.list(limit=3))
#
stripe.api_key = stripe_keys["secret_key"]


@app.route('/')
def index():
    domain = request.url_root.split(
        "https://")[-1].split("http://")[-1].replace("/", "")
    return render_template("index.html", domain=domain, didkit_version=didkit.getVersion())


@app.route("/", methods=['POST'])
def index_post():
    email = request.form['email']
    return redirect(f'/signIn/{email}')


@app.route('/new-patient', methods=['POST', 'GET'])
def new_patient():
    if request.method == 'POST':
        if request.form.get('privacy'):
            email = request.form['email']
            return redirect(f'/signIn/{email}')
    return render_template('new-patient.html')


@app.route('/signIn/<email>')
def signIn(email):

    session = workos_client.passwordless.create_session(
        {'email': email, 'type': 'MagicLink'}
    )
    # Send a custom email using sendgrid
    # sendEmail(session['link'], email)

    # Send email using workos
    workos_client.passwordless.send_session(session['id'])
    return render_template('send-link.html', email=email)


@app.route('/manage-account')
def manageAccount():
    return render_template('manage-account.html')


@app.route("/success")
def success():
    credential = json.dumps(issueCredential(request), indent=2, sort_keys=True)

    # workos magic link w/ flask email
    credential = json.loads(credential)
    email = credential['credentialSubject']['email']
    print(f'sentEmail: {email}', file=sys.stderr)
    return redirect(f'/signIn/{email}')


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
    print("code: " + code)
    profile_and_token = workos_client.sso.get_profile_and_token(code)

    # Use the information in `profile` for further business logic.
    profile = profile_and_token.profile
    # print("profile: " + profile)
    # return jsonify({"status": "success", "user": profile.raw_attributes})
    return redirect('/manage-account')


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


def sendEmail(body, address):
    #pylint: disable=no-member
    key = os.environ.get('SENDGRID_API_KEY')
    print(key, file=sys.stderr)
    message = Mail(
        from_email='support@hieofone.com',
        to_emails=address,
        subject='HEI OF ONE Login Link',
        html_content=body)
    try:
        sg = SendGridAPIClient(key)
        response = sg.send(message)
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(e.message)
