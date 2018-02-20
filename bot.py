#!/usr/bin/env python
__version__ = '0.0.1'
import configparser
import json
import logging
import os
import string
from datetime import datetime
from io import StringIO, BytesIO
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, Document)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler)
# from telegram.ext.dispatcher import run_async
from guldledger import *

config = configparser.ConfigParser()
config.read('config.ini')
COMMODITIES = json.loads(config['telegram']['COMMODITIES'])

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

NAMECHARS = set(string.ascii_lowercase + string.digits + '-')

UPLOADPGPKEY, SIGNTX, WELCOME, CANCEL = range(4)


def start(bot, update):
    update.message.reply_text(
        'Hi! My name is Gai, a guld-ai. I can help you with your guld related data and requests. I always respond from the perspective of guld founder, isysd.\n\n'
        'Commands:\n\n'
        '  /price <asset>\n'
        '  /balance <account> [value_in]\n'
        '  /asl <account> [value_in]\n'
        '  /txgen <type> [args*]\n'
        '    /txgen register individual <name>\n'  # TODO group or device
        '    /txgen transfer <from> <to> <amount> [commodity]\n'
        '    /txgen grant <contributor> <amount> [commodity]\n'
        '  /txsub [signed_tx]\n'
        '  /apply <username> <pgp-rsa-2048+pub-key>\n'  # TODO group or device
    )
    return


def price(bot, update, args):
    # user = update.message.from_user
    if len(args) == 0:
        update.message.reply_text('Invalid commodity. Options are: %s' % ", ".join(COMMODITIES))
    else:
        commodity = str(args[0]).upper()
        if commodity not in COMMODITIES:
            update.message.reply_text('Invalid commodity. Options are: %s' % ", ".join(COMMODITIES))
        else:
            update.message.reply_text("%s = $%s" % (commodity, get_price(commodity)))
    return


def assets_liabilites(bot, update, args):
    if len(args) == 0:
        update.message.reply_text('username is required.')
    else:
        username = str(args[0])
        if len(args) > 1:
            bals = get_assets_liabs(username, in_commodity=str(args[1]))
        else:
            bals = get_assets_liabs(username)
        bals = (bals[:500] + '..') if len(bals) > 500 else bals
        update.message.reply_text(bals)
    return



def balance(bot, update, args):
    if len(args) == 0:
        update.message.reply_text('username is required.')
    else:
        username = str(args[0])
        if len(args) > 1:
            bals = get_balance(username, in_commodity=str(args[1]))
        else:
            bals = get_balance(username)
        bals = (bals[:500] + '..') if len(bals) > 500 else bals
        update.message.reply_text(bals)
    return


def txgen(bot, update, args):
    tguser = update.message.from_user
    txtype = args[0]
    dt, tstamp = get_time_date_stamp()
    fname = '%s.dat' % tstamp
    if txtype in ['reg', 'register']:
        utype = args[1]
        message = gen_register_individual(args[2], dt, tstamp)
        update.message.reply_document(document=BytesIO(str.encode(message)),
            filename=fname,
            caption="Please PGP sign the transaction file or text and send to the /txsub command:\n\n"
        )
        bot.send_message(chat_id=update.message.chat_id, text=message)
    elif txtype in ['send', 'transfer']:
        if len(args) > 4:
            commodity = args[4]
        else:
            commodity = 'GULD'
        message = gen_transfer(args[1], args[2], args[3], commodity, dt, tstamp)
        update.message.reply_document(document=BytesIO(str.encode(message)),
            filename=fname,
            caption="Please PGP sign the transaction file or text and send to the /txsub command:\n\n"
        )
        bot.send_message(chat_id=update.message.chat_id, text=message)
    elif txtype in ['grant', 'issue']:
        amount = args[2]
        if len(args) > 3:
            commodity = args[3]
        else:
            commodity = 'GULD'

        message = gen_grant(args[1], args[2], commodity, dt, tstamp)
        update.message.reply_document(document=BytesIO(str.encode(message)),
            filename=fname,
            caption="Please PGP sign the transaction file or text and send to the /txsub command:\n\n"
        )
        bot.send_message(chat_id=update.message.chat_id, text=message)
    else:
        update.message.reply_text('Unknown transaction type.')
    return


def application(bot, update, args):
    if len(args) < 2:
        update.message.reply_text('username and pgp pubkey are required arguments')
        return
    message = update.message.text[update.message.text.find(' '):].strip(' ')
    divi = message.find(' ')
    name = message[:divi].strip(' ').lower()
    pubkey = message[divi:].strip().replace('—', '--')
    if not all(c in NAMECHARS for c in name) or len(name) < 4:
        update.message.reply_text('Guld names must be at least 4 characters and can only have letters, numbers, and dashes (-).')
        return
    elif (len(pubkey) < 500 or
            not pubkey.startswith('-----BEGIN PGP PUBLIC KEY BLOCK-----') or
            not pubkey.endswith('-----END PGP PUBLIC KEY BLOCK-----')):
        update.message.reply_text('Please submit a valid, ascii-encoded PGP public key (RSA 2048+ bit) as a message.')
        return
    else:
        fpath = os.path.join(GULD_HOME, 'ledger', 'GULD', name)
        keypath = os.path.join(GULD_HOME, 'keys', 'pgp', name)
        try:
            os.makedirs(fpath)
            os.makedirs(keypath)
        except OSError as exc:
            if exc.errno == os.errno.EEXIST and os.path.isdir(os.path.join(GULD_HOME, 'ledger', 'GULD', name)):
                update.message.reply_text('That name is taken. Did you take it? Applying anyway, since we are in onboarding phase.')
            else:
                update.message.reply_text('Error reserving name. Try another one.')
            # return
        fpr = import_pgp_key(name, pubkey)
        if fpr is not None:
            update.message.reply_text('Application submitted, pending manual approval.\n\nname:        %s\nfingerprint: %s' % (name, fpr))
        else:
            update.message.reply_text('Unable to process application.')


def signed_tx(bot, update):
    if update.message.text != '/txsub':
        sigtext = update.message.text[7:].replace('—', '--')
        name = get_signer_name(sigtext)
        if name is None:
            update.message.reply_text('Invalid or untrusted signature.')
        else:
            rawtx = strip_pgp_sig(sigtext)
            txtype = get_transaction_type(rawtx)
            tstamp = get_transaction_timestamp(rawtx)
            if txtype is None:
                update.message.reply_text('ERROR: Unknown transaction type')
                return
            ac = get_transaction_amount(rawtx)
            if ac is None:
                update.message.reply_text('ERROR: Unknown transaction format')
                return
            amount, commodity = ac
            fname = '%s.dat' % tstamp
            fpath = os.path.join(GULD_HOME, 'ledger', commodity, name, fname)

            def write_tx_files():
                with open(fpath + '.asc', 'w') as sf:
                    sf.write(sigtext)
                    with open(fpath, 'w') as f:
                        f.write(rawtx)
                update.message.reply_text('Message submitted.')

            if os.path.exists(fpath):
                update.message.reply_text('Message already known.')
                return
            elif txtype == 'transfer':
                write_tx_files()
            elif txtype == 'register individual':
                bal = get_guld_sub_bals(name)
                if 'guld:Income:register:individual' in bal:
                    update.message.reply_text('ERROR: Name already registered.')
                else:
                    write_tx_files()
            elif txtype == 'grant':
                if (float(amount) < 10 and name in ['fdreyfus', 'isysd', 'cz', 'juankong', 'aldo'] or
                    name in ['isysd', 'cz']):
                    write_tx_files()

    return


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    updater = Updater(config['telegram']['bottoken'])

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", start))
    dp.add_handler(CommandHandler("price", price, pass_args=True))
    dp.add_handler(CommandHandler("balance", balance, pass_args=True))
    dp.add_handler(CommandHandler("bal", balance, pass_args=True))
    dp.add_handler(CommandHandler("asl", assets_liabilites, pass_args=True))
    dp.add_handler(CommandHandler("txgen", txgen, pass_args=True))
    dp.add_handler(CommandHandler("txsub", signed_tx))
    dp.add_handler(CommandHandler("apply", application, pass_args=True))

    # register_handler = ConversationHandler(
    #     entry_points=[CommandHandler('register', register, pass_args=True)],
    #
    #     states={
    #         UPLOADPGPKEY: [MessageHandler(Filters.text, upload_pgp_key)],
    #         SIGNTX: [MessageHandler(Filters.text, signed_tx)],
    #         WELCOME: [MessageHandler(Filters.text, welcome_newuser)],
    #         CANCEL: [CommandHandler('cancel', cancel)]
    #     },
    #
    #     fallbacks=[CommandHandler('cancel', cancel)]
    # )
    #
    # dp.add_handler(register_handler)

    dp.add_error_handler(error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
