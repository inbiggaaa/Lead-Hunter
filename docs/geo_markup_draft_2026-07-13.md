# Черновик гео-разметки: 518 активных каналов без города

**Дата:** 13.07.2026. **Статус: ЧЕРНОВИК — ничего не применено, ждёт проверки владельца.**

Источник: все каналы `catalog_channels` с `is_ignored=false`, без `auto_matched_city_id` и без строк в `channel_cities`. Разметка вручную по username + названию. Города — только из текущего справочника `cities`.

## Сводка

| Класс | Кол-во | Действие |
|---|---|---|
| 🏙 Город из справочника | 21 | SQL §2 — применить после проверки |
| 🗑 Мусор (не та страна / не гео) | 107 | SQL §3 — `is_ignored=true` |
| 🔀 Смена страны | 3 | §4 — вручную/SQL после решения |
| 🆕 Город отсутствует в справочнике | 49 | §5 — сначала решить, добавлять ли города |
| ⚠️ Пограничные | 5 | §6 — город есть, но канал сомнительный |
| 🌍 Общестрановые (норма, оставить) | 333 | §7 — без изменений |

Ключевые находки:
- **107 каналов — мусор**: серия «страны мира» в ОАЭ (Гана, Габон, Вануату…, 24 шт.), московские ЖК «Испанские кварталы»/Коммунарка в Испании, оптовые доски РФ в Южной Корее, аниме/гемблинг-чаты во Вьетнаме. Они не приносят лидов и портят каталог при активации этих стран.
- **У Южной Кореи в справочнике нет ни одного города** (даже Сеула). У Китая только Пекин/Шанхай, при этом 14 каналов — других городов.
- Общестрановые каналы («Виза», «Работа», «Барахолка страны») — это норма: по логике доставки они отдаются и city-подписчикам.

## §2. Привязки к существующим городам (21) — SQL готов

    -- Привязки к существующим городам (channel_cities + auto_matched_city_id если NULL)
    BEGIN;
    -- bar_chernogoriya → Бар [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (256, 453) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 453 WHERE id = 256 AND auto_matched_city_id IS NULL;
    -- cangguchat — Чангу, 3778 уч. → Бали [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (363, 7) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 7 WHERE id = 363 AND auto_matched_city_id IS NULL;
    -- phanthiet_chat — Фантьет, агломерация с Муйне → Муйне [сред]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (376, 6) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 6 WHERE id = 376 AND auto_matched_city_id IS NULL;
    -- byenos_aires — экспаты БА → Буэнос-Айрес [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (468, 88) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 88 WHERE id = 468 AND auto_matched_city_id IS NULL;
    -- buenosairesrent → Буэнос-Айрес [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (474, 88) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 88 WHERE id = 474 AND auto_matched_city_id IS NULL;
    -- arglem — Лемос, пригород БА → Буэнос-Айрес [низк]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (485, 88) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 88 WHERE id = 485 AND auto_matched_city_id IS NULL;
    -- kair_egipet — сеть *_egipet, вкладка Cairo → Каир [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (602, 438) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 438 WHERE id = 602 AND auto_matched_city_id IS NULL;
    -- fudjeira_chat — сеть *_chat, вкладка «общий» → Фуджейра [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (628, 100) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 100 WHERE id = 628 AND auto_matched_city_id IS NULL;
    -- gstoremobilefzco — GStore, магазин в Дубае → Дубай [низк]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (631, 99) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 99 WHERE id = 631 AND auto_matched_city_id IS NULL;
    -- chat_cairo → Каир [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1169, 438) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 438 WHERE id = 1169 AND auto_matched_city_id IS NULL;
    -- Chat_english_Cairo — англ. курсы в Каире → Каир [сред]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1176, 438) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 438 WHERE id = 1176 AND auto_matched_city_id IS NULL;
    -- congdongphuquoc_chat — вьетнамоязычный → Фукуок [сред]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1238, 5) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 5 WHERE id = 1238 AND auto_matched_city_id IS NULL;
    -- ubudiy_chat → Убуд [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1486, 442) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 442 WHERE id = 1486 AND auto_matched_city_id IS NULL;
    -- parq_ubud_chatbot — PARQ Ubud → Убуд [низк]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1487, 442) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 442 WHERE id = 1487 AND auto_matched_city_id IS NULL;
    -- dahabs_chat → Дахаб [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1587, 441) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 441 WHERE id = 1587 AND auto_matched_city_id IS NULL;
    -- canggu_chat — Чангу, район Бали → Бали [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1670, 7) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 7 WHERE id = 1670 AND auto_matched_city_id IS NULL;
    -- pandasurfcangguchat — Чангу → Бали [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1671, 7) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 7 WHERE id = 1671 AND auto_matched_city_id IS NULL;
    -- sharm_eli_sheih → Шарм-эш-Шейх [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1952, 437) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 437 WHERE id = 1952 AND auto_matched_city_id IS NULL;
    -- ABU_DABI_OFFICIAL_CHAT → Абу-Даби [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1982, 152) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 152 WHERE id = 1982 AND auto_matched_city_id IS NULL;
    -- chat_batumy → Батуми [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (1999, 64) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 64 WHERE id = 1999 AND auto_matched_city_id IS NULL;
    -- batumy_chat → Батуми [выс]
    INSERT INTO channel_cities (channel_id, city_id) VALUES (2000, 64) ON CONFLICT DO NOTHING;
    UPDATE catalog_channels SET auto_matched_city_id = 64 WHERE id = 2000 AND auto_matched_city_id IS NULL;
    COMMIT;

## §3. Мусор → is_ignored (107)

Полный список с причинами:

### Вьетнам (14)
- `Dating_Chat_Latvia` — Знакомства Наших в Латвии 🇱🇻 Чат | Dating Latvia Chat → Латвия, не Вьетнам (Dating Latvia)
- `chatmariadance` — чат Bachata & Latin dance с Марией → танц-чат без гео
- `masterdancek` — LADY DANCE LATINA Chat🤍 → танц-чат без гео
- `hoinhomhentai` — Anime VN Chat → вьетн. аниме-чат
- `Fukuoka_Chat` — Чатик → Fukuoka = Япония, не Фукуок
- `dandgella` — Late night school🖤 Chat → 'Late night school', не гео
- `toplatindancechat` — Top Latin Dance chat → танц-чат без гео
- `AEgamerOE777` — Hội Anh Em OE777 Chat → вьетн. гемблинг OE777
- `danylater` — later<3 Chat → фан-чат без гео
- `neshinsan_muichiro1edit` — neshinsan chati → аниме-эдиты
- `muichiro_needL` — mui_talking chat → аниме-эдиты
- `vietnam_jobs` — Jobs Vietnam (all cities) → битый username (ValueError), «all cities»
- `vietnam_general` — Stake chính thức → гемблинг Stake (vietnam_general)
- `club_tochka_rosta` — ВЫСТAВКИ В РОССИИ → «ВЫСТАВКИ В РОССИИ» (club_tochka_rosta)

### Грузия (4)
- `briese_chat` — Briese Crewing Russia | Georgia | Ukraine chat → крюинг моряков Briese, не гео
- `spb_fulfillment` — 3,898 — Фулфилмент Санкт-Петербург/ ФФ СПБ /Фулфилмент в спб → фулфилмент СПб
- `mezgorodru` — АНОНСЫ ВЫСТАВОК НА 2024 ГОД → «АНОНСЫ ВЫСТАВОК» РФ
- `issik_kul2019` — 2,368 — Иссык-куль & Грузия 2023 → Иссык-Куль (Киргизия), полумёртвый

### Египет (17)
- `Geography_Optional_UPSC_2025s` — Geography Optional Shabbir Sir Himanshu Sharma Rushikesh Dud → индийский экзамен UPSC
- `SharmBengal` — Russia 🇷🇺 CATS and KITTENS for SALE → продажа кошек РФ
- `fantasiko_chat` — ديربي القاهرة | Cairo Derby → арабский футбольный фан-чат
- `Sky_cairo_chat` — سَكاي.") → арабский чат без гео
- `CAIROERC_CHAT` — $CAIRO The Alpha Dog → крипто-мем $CAIRO
- `KAIROSPAY_CHAT` — KAIROSPAY EXCHANGE Чат | вопросы и отзывы → обменник KAIROSPAY, не гео
- `Geography_Optional_UPSC_2027` — Geography Optional Shabbir Sir Himanshu Sharma Rushikesh Dud → индийский экзамен UPSC
- `stodevyanostik1` — 𝕾𝖍𝖆𝖗𝖒𝖆𝖝 𝕻𝖔𝖜𝖊𝖗𝖒𝖆𝖝 𝟙𝟡𝟘 | 𝟙𝟝𝟡 𝕽𝖀𝕾 🇷🇺 | → мото Sharmax
- `sharmiis_chat` — чатик с Ксюшкинс → «чатик с Ксюшкинс»
- `ruslansharmax` — 𝕽𝖚𝖘𝖑𝖆𝖓 на 𝕾𝖍𝖆𝖗𝖒𝖆𝖝 → мото Sharmax
- `shrmaxrus` — 𝑺𝑯𝑨𝑹𝑴𝑨𝑿 𝑹𝑼𝑺 → мото Sharmax
- `SHARM_UC_CHAT` — SHARM UC SHOP CHAT → PUBG UC shop
- `iracairokundalini` — IRA CAIRO | YOGA Chat → йога-блог (Cairo — имя)
- `dahabountychat` — 𝐛𝐨𝐮𝐧𝐭𝐲💘 Chat → «bounty», не Дахаб
- `cairoqme` — novoseltsevaa Chat → личный чат-блог
- `Sharms_chat` — Sharms chat → пустой чат, 1 уч.
- `sharm_chat1` — Эликсир вечного шарма Chat → «эликсир шарма», не Шарм

### Индия (1)
- `copsgps` — 1,943 — Cops GPS → Cops GPS, не гео

### Испания (11)
- `fckngbarber` — FCKNG Barbers Community Chat → барбер-комьюнити без гео
- `cordobaspainchatt` — ох софико chat → title-мусор, 5 уч. (cordobaspainchatt)
- `CHAT_spain_rus_esp` — ЧАТ Испанский онлайн → курсы испанского онлайн
- `DahaBarberChat` — DahaBarber Chat → барбер-чат без гео
- `valensiaartist_chat` — Валентина Смирнова: Художник комментарии → художник Валентина (не Валенсия)
- `uslugikommunarka` — 659 — КОММУНАРКА / БУТОВО / РЕКЛАМА / УСЛУГИ → Коммунарка, Москва
- `visa_family_agency` — 2,483 — VISA FAMILY 🇺🇸 / БОТ США → визы США
- `detskayabarakholka_ik_np` — Детская барахолка / Объявления Испанские кварталы, НП, НХ, П → ЖК «Испанские кварталы», Москва
- `saprokshino` — 9,510 — САЛАРЬЕВО , ПРОКШИНО, ИК, ФИЛАТОВ ЛУГ ОБЪЯВЛЕНИЯ → Саларьево/Прокшино, Москва
- `obiyavleniya_ispanckie_kv` — Объявления / Барахолка Испанские кварталы, Николин парк, Про → ЖК «Испанские кварталы», Москва
- `rurdhzdtezruxi` — 7,719 — Акции, Услуги, Товары Коммунарка → Коммунарка, Москва

### ОАЭ (27)
- `rixos_uae_for_russia_ej` — BongaCams StripChat ChatUrbate → спам BongaCams
- `avtobroker30` — 2,290 — «GREEN LINE» АВТО, СПЕЦТЕХНИКА,АВТОЗАПЧАСТИ из ОАЭ-Р → авто-брокер Астрахань
- `kosmolux` — 198 — ТЕСТЕРЫ •СЕЛЕКТИВ• БРЕНДОВЫЕ СУМКИ 🛍 KOSMOLUX54 → косметика Новосибирск
- `gana_chat` — Гана — Аккра → Гана
- `gabon_ru` — Габон — Либревиль → Габон
- `avia_tashkent` — 188 — aviakassa-TOSHKENT → авиакасса Ташкент
- `dominica_chatik` — Доминика — Розо → Доминика
- `gaiana_chat` — Гайана — Джорджтаун → Гайана
- `salwador_chat` — Сальвадор — Сан-Сальвадор → Сальвадор
- `redsunavto_chat` — 4,516 — Автомобили на заказ СПб / Германия Япония Корея / Ча → авто СПб
- `kamerun_chat` — Камерун — Яунде → Камерун
- `vanuatu_ru` — Вануату — Порт-Вила → Вануату
- `ruanda_chat` — Руанда — Кигали → Руанда
- `batareyka125rus` — 3,351 — Батарейка25 - авто из Японии, Кореи и ОАЭ → авто Владивосток
- `martinika_chat` — Мартиника — Фор-де-Франс → Мартиника
- `nauru_chat` — Науру — Ярен → Науру
- `namibiya_chat` — Намибия — Виндхук → Намибия
- `macedoniya_chat` — Северная Македония — Скопье → Сев. Македония
- `pyerto_riko` — Пуэрто-Рико — Сан-Хуан → Пуэрто-Рико
- `surinam_chat` — Суринам — Парамарибо → Суринам
- `caboverde_chat` — Кабо-Верде — Прая → Кабо-Верде
- `tunis_ru` — Тунис — Тунис → Тунис
- `gaiti_chat` — Гаити — Порт-о-Пренс → Гаити
- `gonduras_chat` — Гондурас — Тегусигальпа → Гондурас
- `vip_real_estate_sochi` — Недвижимость в Сочи🌴 → недвижимость Сочи
- `gvatemala_chat` — Гватемала — Гватемала → Гватемала
- `sentlusiya` — Сент-Люсия — Кастри → Сент-Люсия

### Таиланд (9)
- `GOAT_MILK116_RUS` — Сельский край → «Сельский край», не гео
- `araaaabauajaj` — Чат общения | KrabyxA → фан-чат KrabyxA
- `goal_chat` — GoalHona | Чак Чаки Футбол → футбол
- `Goatereumchat` — Goatereum - Community Chat → крипта Goatereum
- `bingochatphilkoo` — ⋆ ࣪. ༝𝘽𝙄𝙉𝙂𝙊 [чата пхилку]₊˚੭ ˖ → фан-чат
- `goat_chat` — Goat Chat → Goat Chat, не гео
- `UZOQDAGI_YAQINLARIM_CHAT_N1` — Пхй гр😂 → узбекский семейный чат
- `chat_salat` — ПХИХИческое спокойствие → «ПХИХИческое», не Пхи-Пхи
- `chatparkphibrstar` — Чат Парк ПХИБР СТАР 🚕 → таксопарк ПХИБР (РФ?)

### Турция (6)
- `hahafunnysearch` — смешные поисковые запросы wildberries → поисковые запросы WB
- `TurkeyinRussiaaa` — Turkey in Russia Chat → Turkey in Russia (магазин в РФ)
- `mohiro_turkey` — مهاجران ترکیه | Turkey Expats → фарси-чат мигрантов
- `tyrcia_popytchiki` — РАСПИСАНИЕ ВЫСТАВОК В РОССИИ → «РАСПИСАНИЕ ВЫСТАВОК В РОССИИ»
- `turcia_rabota` — РАСПИСАНИЕ ВЫСТАВОК НА 2024 ГОД → «РАСПИСАНИЕ ВЫСТАВОК НА 2024»
- `kavkaz_tir` — КАВКАЗ 🏔 ДАЛЬНОБОЙЩИКИ → дальнобойщики Кавказ

### Черногория (1)
- `cryptosushist` — TON SUSHI BAR CHAT → крипто TON SUSHI

### Шри-Ланка (2)
- `bentoTanya_chat` — БЕНТО|ТОРТЫ|ОРЕНБУРГ Chat → торты Оренбург
- `sale2119` — Барахолка ЖК Кварталы 21/19 / ЖК SREDA → ЖК Москва (sale2119)

### Южная Корея (15)
- `autopartskorea_eurasiamotors` — 1,564 — Автоаксессуары из Кореи 'Eurasia Motors' → автоаксессуары для РФ
- `korenovka` — 949 — Кореновск Ответы → Кореновск, РФ
- `mastercar125chat` — 3,143 — MasterCar125.ru 🚗 → авто Владивосток
- `pro1000parts` — 973 — заведи японца! → авто РФ «заведи японца»
- `ozonfbohelp` — 5,315 — Ozon: поддержка по поставкам FBO → Ozon FBO
- `fishretailtrade` — 1,321 — Fishretail.ru 🐟 Рыба, икра оптом → рыба оптом РФ
- `koreacosmeticshoping_ua` — 1,254 — Корейская косметика → косметика UA
- `meatinfotrade` — 1,940 — Meatinfo.ru 🥩Мясо оптом Доска объявлений → мясо оптом РФ
- `fruitinfo` — 1,326 — Fruitinfo.ru 🍋🍏🥔 Овощи, фрукты оптом → овощи оптом РФ
- `koreastyleua` — 1,735 — Авто из Кореи (обсуждение)🇺🇦🇺🇦🇺🇦 → авто из Кореи UA
- `milknettrade` — 689 — Milknet.ru 🥛🧀 Молоко, сыр оптом → молоко оптом РФ
- `autojpvdk` — 2,535 — 🚙 Заведи японца! 🚗 → авто Владивосток
- `zarabotaispolzoi` — 1,499 — Зарабатываем с пользой!❤️💰🎉 → заработок-спам
- `koreancity_shop` — 1,705 — KoreANCity Магазин Корейской продукции ❤️ → магазин корейских товаров в РФ
- `diatechsauzb` — 387 — Diatech SA - Медицинское оборудование → медоборудование UZ

SQL:

    -- Мусор → is_ignored (страна/тематика не относится к каталогу)
    BEGIN;
    UPDATE catalog_channels SET is_ignored = true WHERE id IN (38, 93, 99, 126, 128, 142, 220, 221, 227, 246, 252, 254, 368, 400, 407, 409, 410, 412, 414, 416, 417, 421, 423, 424, 425, 426, 429, 430, 435, 456, 525, 630, 633, 634, 635, 637, 638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 651, 653, 655, 656, 657, 658, 659, 661, 729, 762, 763, 1038, 1042, 1044, 1045, 1073, 1077, 1078, 1168, 1170, 1172, 1173, 1175, 1294, 1342, 1386, 1446, 1514, 1521, 1582, 1583, 1633, 1635, 1637, 1698, 1734, 1748, 1846, 1912, 1932, 1935, 1936, 1937, 1960, 2052, 2118, 2130, 2131, 2132, 2133, 2134, 2135, 2136, 2137, 2139, 2140, 2243, 2244, 2271, 2301);
    COMMIT;
    -- откат: SET is_ignored = false для тех же id

## §4. Смена страны (3)

| Канал | id | Сейчас | Должно быть | Причина |
|---|---|---|---|---|
| `caesar_resort_chat` | 301 | Кипр | Северный Кипр + Фамагуста (392) | Caesar Resort — комплекс в Искеле, СК |
| `kiriniya` | 319 | Кипр | Северный Кипр + Кирения (города нет в справочнике) | Кирения — город СК |
| `cyprusfood` | 308 | Кипр | Северный Кипр (без города) | «Еда на Кипре (СК)» |

## §5. Города, которых нет в справочнике (49 каналов)

Решение владельца: добавить города в `cities` (появятся в FSM-воронке) или оставить каналы общестрановыми. Группировка:

- **Китай (14):** Чунцин, Харбин, Хайнань (3 канала), Тибет, Нанкин, Циндао, Нинбо, Санья, Далянь, Иу, Шэньчжэнь, Чэнду
- **Шри-Ланка (14):** Велигама (3), Калпития, Элла, Аругам-Бей, Бентота, Ваддува, Берувела, Амбалангода, Ахангама, Пассекуда, Канди, Тринкомали
- **Египет (6):** Марса-Матрух, Марса-Алам, Таба, Эль-Гуна*, Нувейба, Сахл-Хашиш* (*или M2M к Хургаде — рядом)
- **Индия (5):** Бангалор, Калькутта, Ченнай, Кочи, Ауровиль
- **Вьетнам (2):** Халонг (`halong_chat`), Хюэ (`hue_chat`)
- **Франция (2):** Корсика, Реюньон
- **По одному:** Баия-Бланка (Аргентина), Рустави (Грузия), Суматра (Индонезия), Больцано (Италия), Боровое (Казахстан), Ансан (Юж. Корея — городов ЮК нет вообще, включая Сеул)

## §6. Пограничные (5) — город определим, но канал сомнительный

| Канал | id | Город | Сомнение |
|---|---|---|---|
| `ballsaigon86` | 1406 | Хошимин (3) | вьетнамоязычный развлекательный |
| `Thienduongquyong254` | 2138 | Вунгтау (85) | вьетнамоязычный «check»-чат |
| `Buomdemdam14` | 2128 | Хошимин (3) | вьетнамоязычный ночной |
| `DALATb0` | 1871 | Далат (83)? | пустой title, 16 участников |
| `cairo_watch_chat` | 1171 | Каир (438)? | «Cairo watch», 19 участников |

Рекомендация: все 5 → is_ignored (лидов из них не будет), но решение за владельцем.

## §7. Общестрановые — остаются как есть (333)

**Аргентина** (20): `argentina_ru`, `russian_argentina`, `besplatnaia_dosca_obiavleniy`, `chat_argentina_ru`, `argentina_pitomci`, `ruargentinachat`, `argentina_medicina`, `argentinatickets`, `argentina4u`, `sdelavshag`, `argentinachild`, `argentina_rentista`, `argentina_visa`, `argentina_360`, `argentina_relokaciia`, `vyezd_v_argentina`, `argentinarusachat`, `argentina_rusia`, `argentina_forum`, `argentina_bg`

**Армения** (2): `armeniya_ru`, `armeniya_pitomci`

**Вьетнам** (18): `vietnamconnections`, `vietnam_russia_chat`, `vietnambuysell`, `expatsinvietnam`, `news_expats_vietnam`, `expats_4at_vietnam`, `rent_vietnam`, `goviet_chat`, `vietnam_to_russia_2022`, `fem_vietnam`, `vietnam_man`, `chat_vietnam_ru`, `viet_viza`, `vietnamik`, `india_visa_shantiom`, `vietnam_bazaar`, `gid_vietnam`, `dodongchat`

**Грузия** (27): `expats_georgia`, `GeorgiaRelocated`, `expats_ge`, `GeorgienExpats`, `georgiaexpatschat`, `verkhniylarsi`, `poputchiki_gruzia`, `georgiarelocated`, `georgia_finance_chat`, `gruziya_biznes`, `gefreelance`, `geohelp01`, `russiansingeorgia`, `helpgeorgia2022`, `gruziyaa`, `georgiau`, `vyezd_v_georgia`, `gruziya_ekskyrsii`, `vlars_chat`, `georgia_it`, `verhniylars`, `georgiaitjobs`, `gruziya_mastera`, `relogame_georgia`, `relokaciya_gruziya`, `livetogether_georgia_chat`, `community_ge`

**Египет** (28): `oteli_egipet`, `avto_egipet`, `party_egipet`, `ekskursii_egipet`, `viza_egipet`, `vakansii_egipet`, `egipet_baraholka`, `deti_egipet`, `ekspaty_egipet`, `posylki_egipet`, `meditsina_egipet`, `egypt_forum`, `egipet_uslugi`, `egyptnavigator`, `egipet_obmen_valut`, `restorany_egipet`, `egipetdlyvseh`, `egipet_otzyvy`, `zhivotnye_egipet`, `diving_egipet`, `forum_egypt`, `egipetb`, `fem_egipet`, `biznes_egipet`, `kvartiry_doma_egipet`, `kaytserfing`, `egipet_forum`, `transfer_egipet`

**Индия** (3): `indiya_poputchiki`, `forum_india`, `indiya_chat`

**Индонезия** (3): `forum_indonesia`, `visarun`, `friendly_indonesia`

**Испания** (25): `migranty_ispania`, `Spain_Rus_chat`, `SegurosSanitasSPAIN`, `ExpatsinEspana`, `rus_spain24`, `inmueble_enspain`, `digitalvisaspain`, `ispaniya_medicina`, `uaespchat`, `esp_turismo`, `forum_spain`, `chat_spain`, `espagna`, `ispaniya_pitomci`, `visadesp`, `posilkiltk`, `ads_spain`, `ispaniyaa`, `chat_hochu_v_ispaniyu`, `infobots_spain`, `spain_help`, `automotomarketspain`, `esp_dinero`, `pech_kin`, `esp_blabla`

**Казахстан** (1): `kazakhstan_vnj`

**Кипр** (22): `russiancypruschat`, `kipr_arenda`, `cyvisaorg`, `cyprus_women_chat`, `sharabaracyprus`, `cuprus_chatru`, `russian_in_cyprus`, `kipr_popytchiki`, `cypruspropertychat`, `cyprus_nedvizhimost`, `cyprus_femchat`, `cyprusbazarfree`, `exchangefinancebank`, `billboard_cyprus_realestate`, `kipr_tusovki`, `forum_cyprus`, `job_europa`, `cyprusinfo1`, `cylaw`, `kipr_relokaciya`, `poputkancy`, `cyprus_uslugi`

**Китай** (4): `kitai_medicina`, `kitai_ucheba`, `chat_wechat`, `kitai_dostavka_biznes`

**ОАЭ** (5): `avtooae1`, `oae_visa`, `forum_uae`, `ummlatifa_ae`, `oae_gr`

**Северный Кипр** (11): `russiansin_northcyprus`, `surkoncyprus`, `kipr_severnii`, `kipr_chat`, `ncyprusit`, `northern_cyprus_forum`, `northcyprus_chat`, `severnyy_kipr`, `cyprus_north`, `mamukipra`, `severniy_kipr_chat`

**Таиланд** (41): `chat_thailand_rus`, `thaiex`, `Thailand_Chat_russia`, `thailandiaexpats`, `thb_rub_transfers_chat`, `expatsthai`, `chat_thailand_russia`, `Buyer_Thai_Ru_chat`, `tailand_visa`, `visathailand`, `guidethailand`, `tailand_pitomci`, `thai_official`, `tailand_vizaran`, `posylki_tailand`, `to_thai`, `party_tailand`, `tai_nedvizhimost`, `tailand_poputchiki`, `oteli_tailand`, `thailand_help`, `uslugi_tailand`, `aviabilety_tailand`, `pets_tailand`, `medicina_tailand`, `taxi_tailand`, `tailandr`, `biznes_tailand`, `rabota_tayland`, `tailand_avito`, `fem_tailand`, `obmen_valuti_tailand`, `ekskursii_tailand`, `forum_thailand`, `vyezd_v_tailand`, `chat_th`, `chat_thailand`, `tailand_chatu`, `kids_tailand`, `bike_tailand`, `sevencountries`

**Турция** (41): `people_in_turkey`, `rushabibichat`, `Turkey_Rus_chat`, `turkeyexpats`, `party_tursia`, `uslugi_tursia`, `yourealate`, `transfer_tursia`, `turkarenda`, `turciya_biznes`, `forum_turkey`, `turciya_banki`, `baraholka_tursia`, `medicina_tursia`, `oteli_tursia`, `rustyrkey`, `otzovy_tursia`, `relocationguideturkey`, `avto_tursia`, `rabota_tursia`, `sarpi_ge`, `eda_tursia`, `relokaciya_turciya`, `posylki_tursia`, `poputchikturkiye`, `obmen_tursia`, `vnz_tursia`, `women_tursia`, `ekskursii_tursia`, `vyezd_v_turkey`, `arenda_tursia`, `turtsiab`, `gototr`, `turcia_arenda`, `biznes_tursia`, `hiring_relocatin_hr_it`, `turciya_vnj`, `tyrciyachat`, `zhivotnie_tursia`, `dopomoga_turkiye`, `deti_tursia`

**Черногория** (30): `chernogoriya_poputchiki`, `expatsmontenegro`, `specialistsmontenegro`, `vyezd_v_montenegro`, `montenegro_chat`, `montenegrospecialists`, `monte_woman`, `nasnedogonyt`, `uslugimontenegro`, `saleme_realty`, `moneymontenegro`, `chernogoria_rabota`, `vizaranmontenegro`, `chernogoriya_uslugi`, `chernogoria_arenda`, `relocationmontenegro`, `arendacrnagora`, `womensmontenegro`, `montenegro_remont`, `top360_chat`, `saleme_job`, `chatcg`, `chernogoria_realty`, `forum_montenegro`, `chernogoriya_kripta`, `parentsmontenegro`, `chatsmontenegro`, `chernogoriya_tusa`, `chernogoriya_pitomci`, `montenegro_ads`

**Шри-Ланка** (38): `shri_lanka_uslugi`, `shri_lanka_yoga`, `shri_lanka_tranfer`, `shri_lanka_party`, `sri_lanka_pets`, `shri_lanka_visa`, `shri_lanka_air_tickets`, `shri_lanka_med`, `srilanka_forum`, `shri_lanka_hotels`, `poputchiki_srilanka`, `shri_lanka_mamkin_businessman`, `lankaru`, `shri_lanka_ru`, `news_shri_lanka`, `shri_lanka_by_sell`, `shri_lanka_fem`, `fly_srilanka`, `sriktoletit`, `sri_lanka_rf_covid19`, `shri_lanka_surfing`, `shri_lanka_rent`, `sri_lanka_rabota`, `shri_lanka_bike`, `obmen_valut_sri_lanka`, `sri_lanka_otzyvy`, `indianvisa2022`, `slrewiev`, `visa_sri`, `shri_lanka_michelin`, `shri_lanka_prices`, `shri_lanka_inforussian`, `lankaruarenda`, `sri_lanka_fun`, `shri_lanka_insurance`, `shri_lanka_ekskursii`, `shri_lanka_baby`, `srilankadays`

**Южная Корея** (14): `korea_baraholka`, `nepopaldomoichat`, `forum_korea`, `koreainforu`, `chat_vsya_korea`, `southkoreachat`, `mykoreanwork`, `domvkoree`, `arenda_korea`, `group_vsya_korea`, `guidetokorea`, `korea_relokaciya`, `rabota_vsya_korea`, `woman_korea`


## §8. Дополнение 13.07: реальные размеры комьюнити недостающих городов (t.me веб-превью)

Счётчики сняты через публичные страницы t.me (без Telegram API). Сортировка по убыванию.

| Город (нет в справочнике) | Канал | Участников |
|---|---|---|
| **Велигама (Шри-Ланка)** | `shri_lanka_weligama` | **5 578** |
| **Тринкомали (Шри-Ланка)** | `shri_lanka_trincomalee` | **2 933** |
| **Бентота (Шри-Ланка)** | `shri_lanka_bentota` | **2 092** |
| Пассекуда (Шри-Ланка) | `shri_lanka_passekudah_kalkudah` | 1 749 |
| **Шэньчжэнь (Китай)** | `shenchjen_chat` | **1 651** |
| Аругам-Бей (Шри-Ланка) | `shri_lanka_arugambay` | 1 650 |
| Элла (Шри-Ланка) | `shri_lanka_ella` | 1 237 |
| Ансан (Юж. Корея) | `tae_house2` (только жильё) | 1 085 |
| Ахангама (Шри-Ланка) | `shri_lanka_ahangama` | 1 078 |
| **Сахл-Хашиш (Египет)** | `sahlhasheeshe` | **1 037 (390 онлайн!)** |
| Чэнду (Китай) | `chendu_chat` | 994 |
| Амбалангода (Шри-Ланка) | `shri_lanka_ambalangoda` | 932 |
| Канди (Шри-Ланка) | `shri_lanka_kandy` | 884 |
| Берувела (Шри-Ланка) | `shri_lanka_beruwala` | 835 |
| Калпития (Шри-Ланка) | `shri_lanka_kalpitiya` | 800 |
| Ваддува (Шри-Ланка) | `shri_lanka_wadduwa` | 765 |
| Санья (Китай) | `saniya_chat` | 650 |
| Бангалор (Индия) | `bangalorchat` | 547 |
| Марса-Алам (Египет) | `marsaalam_egipet` | 372 |
| Халонг (Вьетнам) | `halong_chat` | 326 |
| Рустави (Грузия) | `rystavi_baraholka` | 315 |
| Иу (Китай) | `iy_chat` | 294 |
| Ауровиль (Индия) | `auroville_chat` | 273 |
| Калькутта (Индия) | `kalkutta_chat` | 234 |
| Ченнай (Индия) | `chennai_ru` | 225 |
| Хюэ (Вьетнам) | `hue_chat` | 219 |
| Больцано (Италия) | `bolcano_chat` | 208 |
| Марса-Матрух (Египет) | `mersamatrukh` | 172 |
| Циндао (Китай) | `cindao_chat` | 150 |
| Баия-Бланка (Аргентина) | `baiya_blanka` | 140 |
| Эль-Гуна (Египет) | `el_guna` | 138 |
| Реюньон (Франция) | `reynion_chat` | 137 |
| Кочи (Индия) | `kochi_india` | 131 |
| Харбин (Китай) | `harbin_chat` | 119 |
| Чунцин (Китай) | `chuncin_chat` | 111 |
| Нувейба (Египет) | `nuveiba` | 100 |
| Хайнань (Китай, 3 канала) | `hainan_*` | 48+59+42 |
| Таба (Египет) | `taba_egipet` | 88 |
| Корсика (Франция) | `corsica_chat` | 84 |
| Далянь (Китай) | `dalian_ru` | 76 |
| Тибет (Китай) | `tibet_chat` | 74 |
| Кирения (Сев. Кипр) | `kiriniya` | 72 |
| Нанкин (Китай) | `nankin_chat` | 71 |
| Нинбо (Китай) | `ninbo_chat` | 57 |
| Боровое (Казахстан) | `borovoe_chat` | 51 |
| Велигама сёрф-школы | `soultemplechat`, `SurfSriLanka…` | 4+4 (мертвы) |
| Суматра (Индонезия) | `sumatra_ru` | канал не существует → ignore |

**Выводы:**
1. **Шри-Ланка — главный кандидат на пополнение справочника**: 12 городов, суммарно ~20 500 участников в живой сети `shri_lanka_*`. Велигама (5,6K) больше любого текущего города ШЛ в справочнике.
2. **Китай**: Шэньчжэнь (1,6K) и Чэнду (1K) стоят добавления; остальные города — чаты по 50–150.
3. **Египет**: Сахл-Хашиш (1K, 390 онлайн) — живейшее комьюнити; вариант — M2M к Хургаде (12 км).
4. **Дыры без каналов вообще**: Сеул, Пусан, Гуанчжоу, Мумбаи — в каталоге и discovered ни одного канала (проверено поиском по названиям). У Юж. Кореи в справочнике 0 городов. Нужен discovery — отдельная задача.

## §9. Дополнение 13.07: 84 приватных TravelAsk-чата внесены в каталог с гео (ПРИМЕНЕНО)

Чаты с ручных подписок аккаунтов (@mill_sofi, @iraluxme) — сняты с watched 12.07, теперь внесены в `catalog_channels` по `-100…`-ID с разметкой по названиям: 84 канала, все со страной, 59 с городом. Приватный чат в каталоге работает в Варианте А полностью: классификация глобальна (`channel_segments` — только буст), гео-фильтр `_dispatch` и тиеринг подхватывают каталожное гео, `_resolve_entity` поллит `-100…`-ID (аккаунт должен быть участником — иначе ValueError в логах).

Создано с `is_active=false` (в FSM-воронке НЕ видны до активации): страны Израиль, Германия, Гонконг, Катар, Камбоджа; города Гуанчжоу, Хайнань, Актау, Костанай, Актобе, Мумбаи, Керала, Бангалор, Гималаи, Мцхета, Макади-Бей, Бентота, Тель-Авив, Эйлат, Хайфа, Дюссельдорф, Берлин, Мюнхен.

Эффект на поллинг: в hot добавляются только «Дананг TravelAsk» (город теста) и «Вьетнам TravelAsk» (общестрановой) — остальные 82 запаркованы до появления подписчиков их гео. `russian_in_cyprus` из того же бэкапа — публичный, уже был в каталоге. Откат: `backups/private_chats_84_rollback_2026-07-13.sql`.
