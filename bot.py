#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__version__ = '0.1.1'
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
from guldlib import *

config = configparser.ConfigParser()
config.read('config.ini')
COMMODITIES = json.loads(config['telegram']['commodities'])
OWNER = config['telegram']['owner']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

NAMECHARS = set(string.ascii_lowercase + string.digits + '-')

UPLOADPGPKEY, SIGNTX, WELCOME, CANCEL = range(4)


def halp(bot, update):
    en = (
        'Hi! My name is Gai, a guld-ai. I can help you with your guld related data and requests. I always respond from the perspective of guld founder, isysd.\n\n'
        'Commands:\n\n'
        '/price [unit]\n'
        '    - Price of a unit\n'
        '/bal <account> [unit]\n'
        '    - Account balance with optional unit\n'
        '/addr <asset> <username>\n'  # TODO group or device
        '    - Get address from me. Deposits converted to GULD at market rate. (max 50)\n'
        '/register individual <name> [qty]\n'  # TODO group or device
        '    - Register an individual, device, or group with quantity.\n'
        '/send <from> <to> <amount> [commodity]\n'
        '    - Transfer to another account. Default unit is GULD.\n'
        '/grant <contributor> <amount> [commodity]\n'
        '    - Grant for contributors. Default unit is GULD.\n'
        '/sub <signed_tx>\n'
        '    - Submit a signed transaction\n'
        '/stat\n'
        '    - Get Guld supply (-Liabilities) and Equity information.\n'
        '/apply <username> <pgp-pub-key>\n'  # TODO group or device
        '    - Apply for an account with a username and PGP key (RSA 2048+ bit)\n'
        )
    update.message.reply_text(en)
    return


def ayuda(bot, update):
    es = (
        '¡Hola! Mi nombre es Gai, un guld-ai. Puedo ayudarte con tus datos y solicitudes relacionadas con guld. Siempre respondo desde la perspectiva del fundador de guld, isysd. \n\n'
        'Comandos: \n\n'
        '/precio [unidad] \n'
        '    - Precio de un unidad \n'
        '/bal <cuenta> [unidad] \n'
        '    - Saldo de cuenta con unidad opcional \n'
        '/dir <activo> <nombre> \n' # TODO grupo o dispositivo
        '    - Obtener dirección de mí. Depósitos convertidos a GULD a tasa de mercado. (max 50) \n'
        '/registro individual <nombre> \n' # TODO grupo o dispositivo
        '    - Registrarse como individuo, maquina, o grupo con cantidad. \n'
        '/env <desde> <a> <cantidad> [unidad] \n'
        '    - Transferir a otra cuenta. La unidad predeterminada es GULD. \n'
        '/grant <contribuidor> <cantidad> [unidad] \n'
        '    - Grant para contribuyentes. La unidad predeterminada es GULD. \n'
        '/ent <signed_tx> \n'
        '    - Enviar una transacción firmada \n'
        '/aplica <username> <pgp-pub-key> \n' # TODO grupo o dispositivo
        '    - Solicite una cuenta con un nombre de usuario y clave PGP (RSA 2048+ bit) \n'
        '/stat\n'
        '    - Obtener Guld suministro (-Liabilidades) e información de Equity.\n'
        '/ayuda\n' # TODO grupo o dispositivo
        '    - Documentación de ayuda detallada en un mensaje.\n'
        )
    update.message.reply_text(es)


def price(bot, update, args):
    # user = update.message.from_user
    if len(args) == 0:
        commodity = 'GULD'
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
        username = str(args[0]).lower()
        if len(args) > 1:
            bals = get_assets_liabs(username, in_commodity=str(args[1]).upper())
        else:
            bals = get_assets_liabs(username)
        bals = (bals[:500] + '..') if len(bals) > 500 else bals
        if bals == '' or len(bals) == 0:
            bals = '0'
        update.message.reply_text(bals)
    return


def balance(bot, update, args):
    if len(args) == 0:
        update.message.reply_text('username is required.')
    else:
        username = str(args[0]).lower()
        if len(args) > 1:
            bals = get_balance(username, in_commodity=str(args[1]).upper())
        else:
            bals = get_balance(username)
        bals = (bals[:500] + '..') if len(bals) > 500 else bals
        if bals == '' or len(bals) == 0:
            bals = '0'
        update.message.reply_text(bals)
    return


def register(bot, update, args):
    dt, tstamp = get_time_date_stamp()
    fname = '%s.dat' % tstamp
    utype = args[0]
    rname = args[1].lower()
    if utype == 'individual':
        message = gen_register(rname, 'individual', 1, dt, tstamp)
    elif utype == 'group':
        if len(args) == 3:
            qty = int(args[2])
            if qty <= 0:
                bot.send_message(chat_id=update.message.chat_id, text="Must be positive number of registrations.")
                return
        else:
            qty = 1
        message = gen_register(rname, 'group', qty, dt, tstamp)
    elif utype == 'device':
        message = gen_register(rname, 'device', 1, dt, tstamp)
    else:
        bot.send_message(chat_id=update.message.chat_id, text="Unknown name type. Options are: individual, group, device")
        return
    update.message.reply_document(document=BytesIO(str.encode(message)),
        filename=fname,
        caption="Please PGP sign the transaction file or text and send to the /sub command:\n\n"
    )
    bot.send_message(chat_id=update.message.chat_id, text=message)
    return


def transfer(bot, update, args):
    dt, tstamp = get_time_date_stamp()
    fname = '%s.dat' % tstamp
    if len(args) > 3:
        commodity = args[3].upper()
    else:
        commodity = 'GULD'
    message = gen_transfer(args[0].lower(), args[1].lower(), args[2], commodity, dt, tstamp)
    update.message.reply_document(document=BytesIO(str.encode(message)),
        filename=fname,
        caption="Please PGP sign the transaction file or text and send to the /sub command:\n\n"
    )
    bot.send_message(chat_id=update.message.chat_id, text=message)
    return


def grant(bot, update, args):
    dt, tstamp = get_time_date_stamp()
    fname = '%s.dat' % tstamp
    amount = args[1]
    if len(args) > 2:
        commodity = args[2].upper()
    else:
        commodity = 'GULD'

    message = gen_grant(args[0].lower(), amount, commodity, dt, tstamp)
    update.message.reply_document(document=BytesIO(str.encode(message)),
        filename=fname,
        caption="Please PGP sign the transaction file or text and send to the /sub command:\n\n"
    )
    bot.send_message(chat_id=update.message.chat_id, text=message)
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
    if update.message.text != '/sub':
        sigtext = update.message.text[5:].replace('—', '--')
        fpr = get_signer_fpr(sigtext)
        if fpr is None:
            update.message.reply_text('Invalid or untrusted signature.')
        else:
            tname = get_name_by_pgp_fpr(fpr)
            trust = get_pgp_trust(fpr)
            rawtx = strip_pgp_sig(sigtext)
            isvalid = is_valid_ledger(rawtx)
            if not isvalid:
                update.message.reply_text('Invalid transaction.')
                return
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
            fpath = os.path.join(GULD_HOME, 'ledger', commodity, tname, fname)

            def write_tx_files():
                with open(fpath + '.asc', 'w') as sf:
                    sf.write(sigtext)
                    with open(fpath, 'w') as f:
                        f.write(rawtx)
                update.message.reply_text('Message submitted.')

            if os.path.exists(fpath):
                update.message.reply_text('Message already known.')
                return
            elif trust >= 1 and txtype == 'transfer':
                if not re.search(' *%s:Assets *%s %s*' % (tname, amount, commodity), rawtx) or float(amount) >= 0:
                    update.message.reply_text('Cannot sign for account that is not yours.')
                    return
                else:
                    asl = get_assets_liabs(tname)
                    aslbal = asl.strip().split('\n')[-1].strip().split(' ')[0]
                    if float(aslbal) + float(amount) < 0:
                        update.message.reply_text('Cannot create transction that would result in negative net worth.')
                        return
                write_tx_files()
            elif trust >= 0 and txtype == 'register individual':
                bal = get_guld_sub_bals(tname)
                if 'guld:Income:register:individual' in bal:
                    update.message.reply_text('ERROR: Name already registered.')
                else:
                    write_tx_files()
            elif trust >= 2 and txtype == 'grant':
                # TODO make this community controlled config file value
                if (float(amount) < 10 and tname in ['fdreyfus', 'isysd', 'cz', 'juankong', 'goldchamp'] or
                    tname in ['isysd', 'cz']):
                    write_tx_files()
    return


def guld_status(bot, update):
    update.message.reply_text(get_guld_overview())
    return


def get_addr(bot, update, args):
    commodity = args[0].upper()
    if commodity not in ('BTC', 'DASH'):
        update.message.reply_text('only BTC and DASH are supported at the moment')
    else:
        counterparty = args[1].lower()
        address = getAddresses(counterparty, OWNER, commodity)[-1]
        update.message.reply_text(address)
    return


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    updater = Updater(config['telegram']['bottoken'])

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", halp))
    dp.add_handler(CommandHandler("help", halp))
    dp.add_handler(CommandHandler("price", price, pass_args=True))
    dp.add_handler(CommandHandler("bal", assets_liabilites, pass_args=True))
    # dp.add_handler(CommandHandler("asl", assets_liabilites, pass_args=True))
    dp.add_handler(CommandHandler("register", register, pass_args=True))
    dp.add_handler(CommandHandler("send", transfer, pass_args=True))
    dp.add_handler(CommandHandler("grant", grant, pass_args=True))
    dp.add_handler(CommandHandler("sub", signed_tx))
    dp.add_handler(CommandHandler("stat", guld_status))
    dp.add_handler(CommandHandler("addr", get_addr, pass_args=True))
    dp.add_handler(CommandHandler("apply", application, pass_args=True))

    dp.add_handler(CommandHandler("ayuda", ayuda))
    dp.add_handler(CommandHandler("precio", price, pass_args=True))
    dp.add_handler(CommandHandler("registro", register, pass_args=True))
    dp.add_handler(CommandHandler("env", transfer, pass_args=True))
    dp.add_handler(CommandHandler("ent", signed_tx))
    dp.add_handler(CommandHandler("dir", get_addr, pass_args=True))
    dp.add_handler(CommandHandler("aplica", application, pass_args=True))

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
