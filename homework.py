import logging
import logging.config
import os
import requests
import sys
import time

from http import HTTPStatus
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import InvalidTokenError


load_dotenv()
PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}
RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
TEXT_ERROR = "sys.exit() из-за отсутствия обязательных переменных окружения:"
TEXT_E = "API возвращает код, отличный от 200:"
HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


logging.basicConfig(
    level=logging.INFO,
    format=('%(asctime)s [%(levelname)s] %(message)s - %(name)s'),
    handlers=[
        logging.FileHandler('main.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler("main.log", maxBytes=50000000, backupCount=5)
logger.addHandler(handler)


def check_tokens():
    """Проверяет доступность обязательных переменных окружения."""
    environment_tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID
    }
    name_tokens = ""
    none_value_flag = True
    for key, value in environment_tokens.items():
        if value is None:
            name_tokens += f"{key} "
            none_value_flag = False
    if none_value_flag is False:
        logger.critical(f"{TEXT_ERROR} {name_tokens}")
        raise InvalidTokenError(f"{TEXT_ERROR} {name_tokens}")
    return none_value_flag


def send_message(bot, message_to_bot):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message_to_bot)
        logger.debug("Сообщение отправлено в чат Telegram")
        return True
    except ApiException as error:
        logger.error(f"Сбой при отправке сообщения в чат Telegram {error}")


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        homework = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException:
        logger.error(
            f"{TEXT_E} {homework.status_code}")
        raise requests.RequestException(f"{TEXT_E} {homework.status_code}")
    if homework.status_code != HTTPStatus.OK:
        raise requests.exceptions.HTTPError()
    return homework.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f"Получен ответ не по типу словаря, {TypeError}")
    if response.get("homeworks") is not None:
        homeworks_value = response["homeworks"]
    else:
        logger.error(f"в ответе API домашки нет ключа homeworks: {KeyError}")
        raise KeyError(
            f"в ответе API домашки нет ключа `homeworks`: {KeyError}")
    if not isinstance(homeworks_value, list):
        raise TypeError(
            "Под ключом `homeworks` данные приходят не в виде списка"
        )


def parse_status(homework):
    """Извлекает статус работы о конкретной домашней работе."""
    if homework.get("homework_name") is not None:
        homework_name = homework["homework_name"]
    else:
        logger.error(f"в словаре отсутствует ключ homework_name: {KeyError}")
        raise KeyError(f"в словаре отсутствует ключ homework_name: {KeyError}")
    if homework.get("status") is not None:
        verdict = homework["status"]
    else:
        logger.error(f"в словаре отсутствует ключ status: {KeyError}")
        raise KeyError(f"в словаре отсутствует ключ status: {KeyError}")
    if verdict == "unknown":
        raise KeyError(f"Домашка {homework_name} без статуса")
    if verdict in HOMEWORK_VERDICTS.keys():
        verdict = HOMEWORK_VERDICTS[verdict]
    else:
        verdict = "не определено"
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = 0
    last_message = ""
    message = ""
    message_with_error = ""
    last_message_with_error = ""
    while True:
        try:
            answer = get_api_answer(timestamp)
            check_response(answer)
            homeworks = answer["homeworks"]
            if not homeworks:
                message = "Отсутствуют изменения по домашним работам"
                if message != last_message:
                    send_message(bot, message)
                    last_message = message
            else:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
                timestamp = int(answer["current_date"])
        except Exception as error:
            message_with_error = f"Сбой в работе программы: {error}"
            if last_message_with_error != message_with_error:
                logger.error(message_with_error)
                if send_message(bot, message_with_error):
                    last_message_with_error = message_with_error
        time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
