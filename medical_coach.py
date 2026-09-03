"""Medical clinic domain knowledge for KUH / Kimyo Hospital sales coaching."""

from __future__ import annotations

MEDICAL_SYSTEM_RU_UZ = """
Ты — AI-помощник менеджера РЕГИСТРАТУРЫ / КОНСУЛЬТАНТА медицинской клиники
Kimyo University Hospital (KUH, Ташкент). НЕ врач, НЕ ставишь диагноз.

Язык ответа: ОБЯЗАТЕЛЬНО два языка в каждом поле — русский + o'zbek (lotin).
Формат полей: как требует JSON схемы (summary_ru / summary_uz и т.д.).

=== РОЛЬ ===
Помогаешь менеджеру:
- быстро понять, чего хочет пациент;
- правильно сориентировать по услугам (без диагноза);
- записать на приём / обследование;
- отработать цену, страх, «подумаю»;
- соблюсти медэтику.

=== ЗАПРЕЩЕНО (do_not) ===
- Ставить/намекать диагноз по телефону («у вас точно…», «это онкология»…)
- Обещать 100% результат лечения / «вылечим гарантированно»
- Давить, стыдить, пугать без необходимости
- Называть препараты/схемы лечения как назначение
- Игнорировать red flags (острые состояния)

=== RED FLAGS → срочно к врачу / скорая ===
Сильная боль в груди, одышка, потеря сознания, паралич, речь «каша»,
кровотечение, высокая температура у ребёнка, беременность + кровотечение,
травма головы, судороги. Менеджер: не консультировать, направить в приём / 103.

=== ЧТО МОЖНО ===
- Спросить жалобу/цель визита простыми словами
- Предложить профиль врача: терапевт, эндокринолог, кардиолог, невролог,
  гинеколог, уролог, ЛОР, офтальмолог, хирургия, УЗИ, МРТ, КТ, анализы, ЭКГ
- Объяснить подготовку к УЗИ/МРТ/анализам (общие правила, без персонального Rx)
- Озвучить ориентир по цене + что входит + что решает врач на приёме
- Зафиксировать: ФИО, телефон, услуга, дата/время, врач/кабинет, комментарий

=== СКРИПТ КАЧЕСТВА (score) ===
10: приветствие+клиника+имя → потребность → экспертиза без диагноза →
    ценность → next step (запись) → подтверждение
7-9: почти всё, мелкие пробелы
4-6: есть контакт, но нет записи / поверхностно
0-3: грубость, медобещания, игнор боли/срочности, только «перезвоните»

=== УСЛУГИ (ориентиры для подсказок) ===
МРТ, КТ, УЗИ (брюшная, щитовидка, малый таз, беременность…),
лаборатория, консультации узких специалистов, эндокринология, терапия 24/7,
реанимация/urgent — только маршрутизация, не лечить по телефону.

=== ТОН ===
Тёплый, спокойный, уважительный. Пациент может быть напуган.
RU + UZ ответы менеджеру — готовые фразы, которые можно скопировать в чат/звонок.

Если есть ТРАНСКРИПТ звонка — опирайся на реальные реплики, цитируй коротко.
"""

# Working phrases — grounded in KUH call patterns (booking close, geo, WA spam, price)
PHRASES = {
    "greet_ru": "Здравствуйте, Kimyo University Hospital, меня зовут {name}. Вы по какому вопросу: приём, УЗИ, МРТ или анализы?",
    "greet_uz": "Assalomu alaykum, Kimyo University Hospital, mening ismim {name}. Qaysi masala: qabul, UZI, MRT yoki tahlil?",
    "need_ru": "Коротко: что беспокоит и что нужно сегодня — консультация врача или обследование (УЗИ/МРТ/анализы)?",
    "need_uz": "Qisqa: nima bezovta va bugun nima kerak — shifokor ko'rigi yoki tekshiruv (UZI/MRT/tahlil)?",
    "no_diag_ru": "По телефону диагноз не ставим — это только врач на приёме. Сейчас выберем направление и время, чтобы не терять день.",
    "no_diag_uz": "Telefonda tashxis qo'ymaymiz — faqat qabulda shifokor. Hozir yo'nalish va vaqtni tanlaymiz, kunni yo'qotmaymiz.",
    "price_ru": "Ориентир по цене скажу сразу и что входит (описание/заключение). Точный объём — после осмотра, без «лишних» назначений по телефону.",
    "price_uz": "Narx orientirini hozir aytaman va nima kirishini. Aniq hajm — ko'rikdan keyin, telefonda ortiqcha tayinlovsiz.",
    "price_hard_ru": "Понимаю про цену. Давайте так: назову сумму и что получите. Если не подойдёт — без давления, подскажу альтернативу по объёму. Устраивает?",
    "price_hard_uz": "Narx tushunarli. Shunday qilamiz: summa va nima olasizni aytaman. Mos kelmasa — bosimsiz, hajm bo'yicha variant. Ma'qulmi?",
    "prep_uzi_ru": "УЗИ: зона какая? Брюшная — обычно натощак (уточню). Паспорт + старые заключения, если есть. Запишу на ближайшее: сегодня после обеда или завтра утром?",
    "prep_uzi_uz": "UZI: qaysi zona? Qorin — odatda och qorin (aniqlayman). Pasport + oldingi xulosa. Yaqin vaqt: bugun tushdan keyin yoki ertaga ertalab?",
    "prep_mrt_ru": "МРТ: какая зона и есть ли направление? Важно: металлы, стимулятор, беременность, сильный страх закрытого. Паспорт с собой. Слот: сегодня к вечеру или завтра до обеда?",
    "prep_mrt_uz": "MRT: qaysi zona va yo'llanma bormi? Muhim: metall, stimulyator, homiladorlik, yopiq joy qo'rquvi. Pasport. Slot: bugun kechga yoki ertaga tushgacha?",
    "urgent_ru": "По описанным симптомам лучше не ждать консультации по телефону — приёмное отделение или 103. Могу сказать, как быстрее доехать до клиники.",
    "urgent_uz": "Belgilar bo'yicha telefonda kutmaslik kerak — qabul yoki 103. Klinikaga tezroq yetish yo'lini aytaman.",
    "book_ru": "Фиксирую запись: сегодня в __:__ или завтра в __:__ — что удобнее? Назовите ФИО и номер, на который придёт подтверждение.",
    "book_uz": "Yozuvni yopaman: bugun soat __:__ yoki ertaga __:__ — qaysi qulay? F.I.Sh va tasdiq keladigan telefonni ayting.",
    "book_confirm_ru": "Повторяю: вы записаны на __.__ в __:__, услуга ___, на имя ___, тел. ___. Если опоздаете больше 15 мин — перенесём. До встречи.",
    "book_confirm_uz": "Takrorlayman: __.__ kuni soat __:__, xizmat ___, ism ___, tel ___. 15 daqiqadan ko'p kechsangiz — ko'chiramiz. Ko'rishguncha.",
    "think_ru": "Ок, подумайте. Чтобы слот не ушёл — держу 2 часа без оплаты. Я сам перезвоню в __:__, не жду что «сами наберёте». Какой вопрос остался: цена, время или страх процедуры?",
    "think_uz": "Mayli, o'ylab ko'ring. Slot ketmasin — 2 soat bepul ushlayman. __:__ da o'zim qo'ng'iroq qilaman. Qolgan savol: narx, vaqt yoki protsedura qo'rquvimi?",
    "geo_ru": "Адрес не диктую 5 минут по телефону — пока за рулём это опасно. Запись уже есть: скину геолокацию в Telegram/WhatsApp. Напишите нам первым «Kimyo» на этот номер — иначе сообщение может не дойти (спам-фильтр).",
    "geo_uz": "Telefon orqali 5 daqiqa manzil aytmayman — rulda xavfli. Yozuv bor: Telegram/WhatsApp ga geo tashlayman. Avval shu raqamga «Kimyo» deb yozing — aks holda spam filtr ushlashi mumkin.",
    "geo_sms_ru": "Локацию отправлю SMS-ссылкой на ваш номер. Подтвердите цифры телефона.",
    "geo_sms_uz": "Lokatsiyani SMS-havola qilib yuboraman. Telefon raqamini tasdiqlang.",
    "wa_spam_ru": "С нашего номера WhatsApp часто не доходит, пока вы сами не напишете. Наберите «Kimyo» нам в чат — сразу вышлю точку и напоминание о записи.",
    "wa_spam_uz": "Bizning raqamdan WhatsApp ko'pincha yetmaydi, toki o'zingiz yozmaguncha. Chatga «Kimyo» deb yozing — nuqta va yozuv eslatmasini yuboraman.",
    "instagram_ru": "Видели нас в Instagram — отлично. Чтобы не потерять время: какая услуга и на когда удобно подойти? Запишу и пришлю адрес.",
    "instagram_uz": "Instagramda ko'rgansiz — yaxshi. Vaqt ketmasin: qaysi xizmat va qachon kelish qulay? Yozib, manzil yuboraman.",
    "missed_call_ru": "Не дозвонились / сброс. Перезвоню один раз через 20–40 мин. Если не ответите — SMS: «Kimyo Hospital, перезвоните *номер* по записи».",
    "missed_call_uz": "Aloqa uzildi. 20–40 daqiqadan keyin bitta qayta chaqiraman. Javob bo'lmasa — SMS: «Kimyo Hospital, yozuv bo'yicha *raqam* ga qo'ng'iroq qiling».",
    "close_force_ru": "Чтобы вы не ждали неделями: есть окно сегодня после 15:00 и завтра до 12:00. Какое берём?",
    "close_force_uz": "Haftalab kutmaslik uchun: bugun 15:00 dan keyin va ertaga 12:00 gacha bo'sh. Qaysini olamiz?",
}

SERVICE_HINTS = {
    "мрт": ("МРТ", "MRT"),
    "mrt": ("МРТ", "MRT"),
    "узи": ("УЗИ", "UZI"),
    "uzi": ("УЗИ", "UZI"),
    "ультразвук": ("УЗИ", "UZI"),
    "кт": ("КТ", "KT"),
    "компьютерн": ("КТ", "KT"),
    "экг": ("ЭКГ", "EKG"),
    "эхо": ("ЭхоКГ", "ExoKG"),
    "анализ": ("лаборатория / анализы", "laboratoriya / tahlillar"),
    "tahlil": ("лаборатория / анализы", "laboratoriya / tahlillar"),
    "кровь": ("лаборатория / анализы", "laboratoriya / tahlillar"),
    "эндокрин": ("эндокринолог", "endokrinolog"),
    "endokrin": ("эндокринолог", "endokrinolog"),
    "щитовид": ("эндокринолог / щитовидка", "endokrinolog / qalqonsimon"),
    "терап": ("терапевт", "terapevt"),
    "terapevt": ("терапевт", "terapevt"),
    "карди": ("кардиолог", "kardiolog"),
    "kardiolog": ("кардиолог", "kardiolog"),
    "невр": ("невролог", "nevrolog"),
    "nevrolog": ("невролог", "nevrolog"),
    "гинек": ("гинеколог", "ginekolog"),
    "ginekolog": ("гинеколог", "ginekolog"),
    "урол": ("уролог", "urolog"),
    "urolog": ("уролог", "urolog"),
    "лор": ("ЛОР", "LOR"),
    "офтальм": ("офтальмолог", "oftalmolog"),
    "глаз": ("офтальмолог", "oftalmolog"),
    "хирург": ("хирург", "jarroh"),
    "педиатр": ("педиатр", "pediatr"),
    "детск": ("детский специалист", "bolalar mutaxassisi"),
    "дермат": ("дерматолог", "dermatolog"),
    "гастро": ("гастроэнтеролог", "gastroenterolog"),
    "ортопед": ("ортопед", "ortoped"),
    "стомат": ("стоматолог", "stomatolog"),
    "маммо": ("маммолог", "mammolog"),
    "онколог": ("онколог (маршрутизация)", "onkolog (yo'naltirish)"),
}


def detect_services(text: str) -> list[tuple[str, str]]:
    t = (text or "").lower()
    found: list[tuple[str, str]] = []
    for key, pair in SERVICE_HINTS.items():
        if key in t and pair not in found:
            found.append(pair)
    return found


def is_urgent(text: str) -> bool:
    t = (text or "").lower()
    flags = (
        "груди", "боль в груди", "сердц", "одышк", "без сознания", "паралич",
        "инсульт", "кровотеч", "судорог", "не дыш", "103", "скорая",
        "потерял сознан", "не чувствует", "речь каша", "травма голов",
        "высокая температура", "температура 39", "температура 40",
        "ko'krak", "yurak", "hansirash", "hushidan", "qon ket", "tutqanoq",
        "falaj", "insult", "nafasi", "qattiq og'riq",
    )
    return any(f in t for f in flags)


def detect_objections(text: str) -> list[str]:
    t = (text or "").lower()
    found = []
    mapping = (
        (("дорого", "qimmat", "дешев", "дешевле"), "price"),
        (("подумаю", "o'ylab", "посоветуюсь", "муж", "жена"), "think"),
        (("в другой", "другая клиник", "boshqa klinika", "конкурент"), "competitor"),
        (("боюсь", "страшн", "qo'rq", "claustrophob", "клаустрофоб"), "fear"),
        (("далеко", "пробк", "не успе", "uzoq"), "logistics"),
        (("диагноз", "что у меня", "опасно ли", "tashxis"), "diag_request"),
    )
    for keys, tag in mapping:
        if any(k in t for k in keys):
            found.append(tag)
    return found
