# Learn English — Onlayn ingliz tili kurslari platformasi

Django asosida qurilgan onlayn ingliz tili kurslari platformasi. Grammatika, lug'at,
reading, writing, speaking va listening skillari bo'yicha kurslar, admin tomonidan
faollashtiriladigan ro'yxatdan o'tish va kurslar katalogi.

## Loyiha tuzilishi

- `config/` — Django sozlamalari (settings, urls)
- `accounts/` — foydalanuvchilar (email orqali kirish), ro'yxatdan o'tish
- `courses/` — kurslar, learning outcomes, skill teglari, enrollment, Part va mashqlar (Listening / Reading)
- `writing/` — Writing testlari (Task 1.1, Task 1.2, Part 2), so'z sanagich va o'quvchi yuborgan ishlar
- `panel/` — adminlar uchun boshqaruv paneli (`/panel/`)
- `core/` — bosh sahifa
- `templates/` — barcha HTML shablonlar
- `static/css/style.css` — asosiy dizayn

## Docker orqali ishga tushirish (tavsiya etiladi)

```bash
# Build qilish va fonda ishga tushirish (migratsiyalar avtomatik bajariladi)
docker compose up -d --build

# Birinchi marta: namuna kurslar va admin yaratish
docker compose exec web python manage.py seed_courses
docker compose exec web python manage.py createsuperuser

# Loglarni ko'rish / to'xtatish
docker compose logs -f web
docker compose down
```

**Kod yozayotganda** `docker compose watch` dan foydalaning — o'zgargan fayllar
qayta build qilmasdan konteynerga avtomatik ko'chiriladi va Django o'zi qayta yuklanadi.
`requirements.txt` o'zgarsa, image avtomatik qayta build qilinadi.

Ma'lumotlar bazasi (SQLite) va yuklangan fayllar `app_data` Docker volume'ida saqlanadi,
shuning uchun konteyner qayta yaratilganda ham yo'qolmaydi. Volume'ni ham o'chirish
uchun: `docker compose down -v` (ehtiyot bo'ling — barcha ma'lumotlar o'chadi).

## HTTPS (Speaking mikrofoni uchun)

Brauzer mikrofonni faqat `https://` sahifalarga va `localhost` ga beradi. Shuning uchun boshqa kompyuter yoki
telefondan `http://192.168.2.72:8000` orqali kirilganda Speaking mashqi mikrofonni ishlata olmaydi.
`docker compose up -d` ikkinchi xizmatni — **https** (nginx, `docker/https/`) ni ham ishga tushiradi:

- Manzil: **https://192.168.2.72:8000/** — avvalgi port, faqat `https://` bilan. `8000` portini endi nginx
  ushlaydi va har bir ulanishning birinchi baytlariga qarab ajratadi: oddiy `http` → Django (avvalgidek),
  TLS (`https`) → https server (`docker/https/stream.conf`). **https://192.168.2.72:8443/** ham ishlaydi.
  Shu kompyuterning o'zida `http://localhost:8000` ham yetarli.
- Speaking'ning «Ready?» sahifasi `http://` orqali ochilsa, **Open the secure page →** tugmasi o'sha sahifaning
  https manziliga olib boradi (login saqlanadi). `http://...:8443` yozilsa, o'zi https ga o'tadi.
- Sertifikatni loyihaning o'z kichik sertifikat markazi (CA) imzolaydi, shuning uchun birinchi kirishda brauzer
  «Подключение не защищено / Your connection is not private» deydi: **Дополнительные (Advanced) → Перейти на сайт
  192.168.2.72 (небезопасно) / Continue**. Shundan keyin mikrofon ishlaydi (Allow so'raladi).
- Ogohlantirishni butunlay yo'qotish uchun har bir qurilmada bir marta **https://192.168.2.72:8443/local-ca.crt**
  ni yuklab, ishonchli markaz sifatida o'rnating:
  - Windows: faylni oching → «Установить сертификат» → «Текущий пользователь» → «Поместить все сертификаты в
    следующее хранилище» → «Доверенные корневые центры сертификации» → Далее → Готово → Да; brauzerni qayta oching.
  - Android: Sozlamalar → Xavfsizlik → Shifrlash va hisob ma'lumotlari → Sertifikat o'rnatish → CA sertifikati.
  - iPhone/iPad: faylni oching → Sozlamalar → Profil → O'rnatish; so'ng Asosiy → Haqida → Sertifikatlarga
    ishonch sozlamalari → yoqing.
- Kompyuter manzili (IP) o'zgarsa, `.env` ga `HTTPS_HOSTS=yangi.ip` (bir nechtasi: `a,b`) yozing va
  `docker compose up -d` qiling: sayt sertifikati yangilanadi, qurilmalarga o'rnatilgan CA o'z kuchida qoladi.
  Port `HTTPS_PORT` bilan o'zgartiriladi (standart 8443).
- Sertifikatlar `https_certs` Docker volume'ida saqlanadi; CA kaliti tashqariga chiqmaydi, faqat ochiq qismi
  (`/local-ca.crt`) beriladi. Django nginx yuborgan `X-Forwarded-Proto` ga faqat `HTTPS_PORT` berilganda ishonadi.

## Docker'siz o'rnatish (lokal)

```bash
# 1. Virtual environment faollashtirish
venv\Scripts\activate          # Windows cmd/PowerShell
source venv/Scripts/activate   # Git Bash

# 2. Kutubxonalarni o'rnatish (agar kerak bo'lsa)
pip install -r requirements.txt

# 3. Migratsiyalarni qo'llash
python manage.py migrate

# 4. Superuser yaratish (admin panel uchun)
python manage.py createsuperuser

# 5. Namuna kurslarni yuklash (ixtiyoriy)
python manage.py seed_courses

# 6. Serverni ishga tushirish
python manage.py runserver
```

Sayt: http://127.0.0.1:8000/
Admin panel: http://127.0.0.1:8000/admin/

## Hozirgi admin (demo)

- Email: `admin@example.com`
- Parol: `admin12345`

Sayt ham, admin panel ham **email + parol** bilan kiradi (login/username yo'q).
Yangi admin yaratganda `createsuperuser` email va parol so'raydi va unga avtomatik
**Admin** roli beriladi.

**Production'ga chiqarishdan oldin bu parolni albatta almashtiring.**

## Rollar

| Rol | Kirgach ochiladi | Imkoniyatlari |
|---|---|---|
| **O'quvchi** (`student`) | `/courses/` | Kurslarni ko'rish, kursga yozilish |
| **Admin** (`admin`) | `/panel/` | Boshqaruv paneli (quyida), saytni ham ko'ra oladi |

- Ro'yxatdan o'tganlar doim **O'quvchi** bo'ladi (formada rol tanlanmaydi).
- Rolni o'zgartirish: `/admin/` → Users → **Role** maydoni (yoki yangi admin uchun `createsuperuser`).
- Admin sayt sarlavhasida **Boshqaruv paneli** tugmasini ko'radi. O'quvchi `/panel/` ga
  kirishga uringanda 403 ("Ruxsat yo'q") sahifasi chiqadi.

## Boshqaruv paneli (`/panel/`)

- **Dashboard** — o'quvchilar soni, faollashtirish kutayotganlar, kurslar, yozilishlar,
  tugatilgan kurslar; kutayotgan o'quvchilarni shu yerning o'zida faollashtirish; top 5 o'quvchi.
- **O'quvchilar** — qidiruv (ism/familiya/email), holat bo'yicha filtr (Faol / Kutilmoqda),
  faollashtirish yoki faolsizlantirish, o'chirish. O'quvchi sahifasida yozilgan kurslari va
  har bir kurs bo'yicha **progress (0–100%)** ni o'zgartirish mumkin.
- **Reyting** — faol o'quvchilar **ball** bo'yicha tartiblanadi. Ball = o'quvchi yozilgan
  barcha kurslardagi progress foizlari yig'indisi. Ball va tugatilgan kurslar soni bir xil
  bo'lsa, o'rin ham bir xil.
- **Kurslar** — ro'yxat (holat, skill, qidiruv), nashr etish/yashirish, o'chirish.
- **Kurslar ro'yxatidagi amallar** — ikonkalar: ✏️ tahrirlash, ↗ saytda ko'rish, 👁 yashirish /
  ☁ nashr etish, 🗑 o'chirish (nomi sichqoncha ustiga olib borilganda ko'rinadi; o'chirishdan oldin so'raladi).
- **Kurs qo'shish / tahrirlash** — nomi, skill, daraja, CEFR nishoni, tavsiflar, o'quv
  natijalari ro'yxati, ko'nikma teglari, nashr etish va «YANGI» belgisi. Nashr etilmagan
  (qoralama) kursni faqat adminlar saytda oldindan ko'ra oladi. Yangi kurs saqlangach uning
  tahrirlash sahifasi ochiladi: u yerda **Mashqlar (Practice)** bo'limi (pastda) bor.
  «Kurs tavsifi», «O'quv natijalari» va «Ko'nikma teglari» bo'limlari `templates/panel/course_form.html` dan
  olib tashlangan (yoki izohga olingan) bo'lsa ham saqlash ishlaydi: sahifa yubormagan bo'limlar va matnlar
  o'zgarmay qoladi.

Panelni sinab ko'rish uchun namuna o'quvchilar yaratish va o'chirish:

```bash
docker compose exec web python manage.py seed_demo_students
docker compose exec web python manage.py seed_demo_students --delete
```

Panel ro'yxatidagi **Yozilganlar** — haqiqiy yozilishlar soni. Kurs sahifasidagi
"16,358 Enrolled" kabi sonlar `seed_courses` bergan demo qiymatlar.

## Testlar

```bash
python manage.py test                           # lokal
docker compose exec web python manage.py test   # Docker'da
```

## Ro'yxatdan o'tish va akkountni faollashtirish

1. Foydalanuvchi `/accounts/register/` sahifasida ism, familiya, tug'ilgan kun, email,
   va parolni kiritadi (alohida login yo'q — email login vazifasini bajaradi).
2. Akkount nofaol (`is_active=False`) holatda yaratiladi va foydalanuvchiga
   "Akkountingizni faollashtirish uchun adminga murojaat qiling" xabari admin
   Telegram linki bilan ko'rsatiladi.
3. Admin `/panel/` → **O'quvchilar** (yoki dashboard) bo'limida **Faollashtirish**
   tugmasini bosadi (`/admin/` → Users → **Active** katakchasi ham ishlaydi).
4. Shundan so'ng foydalanuvchi email va parol bilan to'g'ridan-to'g'ri kiradi.
   Faollashtirilmagan akkount bilan kirishga uringanda ham shu xabar ko'rsatiladi.

Admin Telegram linkini `.env` faylida belgilang:

```
ADMIN_TELEGRAM_URL=https://t.me/username
```

Docker'da `.env` o'zgargandan keyin konteynerni qayta yarating: `docker compose up -d`.

## Kurslar

Kurslar boshqaruv panelidan (`/panel/courses/`) qo'shiladi va tahrirlanadi:
sarlavha, kategoriya (grammar/vocabulary/reading/writing/speaking/listening), daraja,
qisqa tavsif, learning outcomes, skill teglari va boshqalar.

`python manage.py seed_courses` buyrug'i 6 ta namuna kursni (har bir skill bo'yicha
bittadan) avtomatik qo'shadi — rasmlardagi "Health and Wellness with Mixed
Conditionals" kursi ham shular jumlasidan. Buyruq kurslarni **nomi bo'yicha** topadi,
shuning uchun kurs nomlarini o'zgartirgandan keyin uni qayta ishga tushirmang (dublikat yaratadi).

## Practice sahifasi (Part va mashqlar)

Kursda **Part**lar bo'lsa, kurs sahifasi o'rniga mashq sahifasi ochiladi. Part'i yo'q
kurslar avvalgi sahifani ko'rsatadi. Hozir ikkita kursda Part'lar bor (Writing kursi esa Part o'rniga
testlar bilan ishlaydi — pastdagi «Writing (testlar)» bo'limiga qarang).

**Listening** (6 ta Part):

| Part | Nomi | Mashqlar |
|---|---|---|
| 1 | Short replies | 10 |
| 2 | Gap filling | 11 |
| 3 | Speakers | 10 |
| 4 | Map labelling | 11 |
| 5 | Extracts | 10 |
| 6 | Lecture notes | 10 |

**Reading** (5 ta Part, har birida 10 ta mashq): ✍️ Part 1 · Gap filling, 🔗 Part 2 · Matching,
🏷️ Part 3 · Headings, ✅ Part 4 · Multiple choice & True / False, 🧩 Part 5 · Summary & questions.
Barcha 5 Part tayyor (pastda): Part 1 (matndagi bo'sh joylar, 1–6), Part 2 (7–14, gap-variantlar ro'yxati),
Part 3 (15–20, sarlavhalar ro'yxati), Part 4 (21–29, matn va A–D / True-False savollari), Part 5 (30–35,
matndagi bo'sh joylar 30–33 va test savollari 34–35).

- Har bir mashq katakchasida «Exercise» va raqami bor; o'quvchi mashqni bajargan bo'lsa,
  natijasi ham ko'rinadi (**⭐ 0/8**).
- **Key vocabulary.** Admin Part'ga so'zlar kiritgan bo'lsa (pastda), Part kartasida «📚 Key vocabulary · 50 words»
  tugmasi chiqadi. Bosilganda «Hide vocabulary» bo'lib o'zgaradi va so'zlar kartochkalari ochiladi: so'z va talaffuzi,
  o'zbekcha ma'nosi (yashil) va misol (3 ustun; planshetda 2, telefonda 1). Tepada qidiruv maydoni bor: u so'z,
  ma'no va misoldan qidiradi, katta-kichik harf va apostrof turlarini (`'`, `ʻ`, `’`) farqlamaydi, bir nechta so'z
  yozilsa hammasi bitta kartada bo'lishi kerak. So'z kiritilmagan Part'da tugma ko'rinmaydi. Tugma
  JavaScript'siz ham ochiladi (faqat qidiruv maydoni JavaScript talab qiladi). Listening va Reading'da bir xil ishlaydi.
- Part va mashqlarni yaratish: `docker compose exec web python manage.py seed_listening_parts` yoki
  `seed_reading_parts` (qayta ishga tushirish xavfsiz: mavjud Part'larni o'zgartirmaydi, faqat yetishmaganini qo'shadi).
  Reading uchun Part 1 mashqlari 8 daqiqa bilan yaratiladi.
- Part nomi va mashq sonini `/admin/` → **Parts** bo'limida o'zgartirish mumkin.
- Mashq katakchasini bosganda mashq sahifasi ochiladi (kirish talab qilinadi):
  1. **Ready to start?** — «1 part · 8 questions · 5 minutes» va **Start exercise 🚀** tugmasi;
  2. mashq sahifasi — taymer (oxirgi 3 daqiqada qizil), **Pause**, audio pleyer va savollar (turiga qarab);
  3. **Submit all parts** bosilganda avval ogohlantirish chiqadi («You still have 8 unanswered questions.
     Submit all parts now? You cannot change answers after this.» — **Yes, submit** / **Keep working**).
     Vaqt tugasa, javoblar so'ralmasdan o'zi yuboriladi;
  4. natijalar sahifasi (Reading'da audio va Transcript o'rniga javoblar bilan matn chiqadi):
     «💪 Keep going! 3 / 8 correct (38%) · Time used: 01:05», **Try again** va
     **More exercises** tugmalari, **All answers** jadvali (har savol uchun sizning javobingiz va to'g'ri javob),
     **Transcript** (audio matni, to'g'ri javoblar sariq rangda — admin kiritgan bo'lsa), audio pleyer va har bir
     savol to'g'ri javobi belgilangan holda. Eng yaxshi natija katakchada ⭐ bilan ko'rinadi.
- Mazmuni to'ldirilmagan mashqda Start tugmasi o'chirilgan va «not ready yet» yozuvi chiqadi.
- Tugma matni **Submit all parts**. Savol raqamlari Part'lar bo'ylab davom etadi.

### Part turlari

Har bir Part'ning o'z **turi** bor (Part sahifasidagi «Mashq turi»), u savollar ko'rinishini va
tekshirilishini belgilaydi. «Birinchi savol raqami» shu Part savollari qaysi raqamdan boshlanishini aytadi.

| Part | Tur | Savollar | Qanday ko'rinadi |
|---|---|---|---|
| 1 · Short replies | Variantlardan tanlash | 1–8 | har savolda A, B, C variantlari (radio) |
| 2 · Gap filling | Eshitib yozish | 9–14 | sarlavha (masalan «Video game review») va bo'sh joylar: oldingi/keyingi matn + yozish maydoni |
| 3 · Speakers | Ro'yxatdan tanlash | 15–18 | variantlar ro'yxati (A–F) va har savolda «Choose an answer...» ro'yxati |
| 4 · Map labelling | Xaritada belgilash | 19–23 | audio, ko'rsatma va xarita rasmi; har joy nomi («Gift shop») ostida A–I harf tugmalari |
| 5 · Extracts | Variantlardan tanlash | 24–29 | har savolda A, B, C; savoldan oldin «Extract One · You hear...» kartochkasi, savol raqami matn bilan bir qatorda |
| 6 · Lecture notes | Eshitib yozish | 30–35 | sarlavha («Labyrinths»), gapli qatorlar va ular orasida gapsiz oddiy qator («Labyrinths represent a journey through life.») |
| Reading 1 · Gap filling | Matndagi bo'sh joylar | 1–6 | audiosiz: sarlavha («Olivia»), katta matn va uning jumlalari ichida «(Q1) 1 [yozish maydoni]» |
| Reading 2 · Matching | Ro'yxatdan tanlash | 7–14 | audiosiz: «Each statement is used once. Two are extra!», A–J ro'yxati va har abzas ostida «Choose an answer...» |
| Reading 3 · Headings | Ro'yxatdan tanlash | 15–20 | audiosiz: sarlavha («Pedestrian Zones and Their Growth»), A–H sarlavhalar ro'yxati; har abzas «15. Paragraph I» qalin yozuvi va matni bilan |
| Reading 4 · Multiple choice & True / False | Variantlardan tanlash (matn bilan) | 21–29 | audiosiz: «Read the following text for questions 21-29.», sarlavha («Eating meat»), abzaslar; undan keyin «Questions 21-24: choose the correct answer A, B, C or D.» kartochkasi va A–D savollari |
| Reading 5 · Summary & questions | Matn: bo'sh joylar + test | 30–35 | audiosiz: matn ichida «(Q30) 30 [yozish maydoni]» (30–33), undan keyin test savollari 34–35 |

Eshitib yozishda javob katta-kichik harfga va ortiqcha probellarga e'tibor bermay tekshiriladi.
Bir nechta javob qabul qilinsa, ularni `/` bilan ajrating (`space station / futuristic city`).
Part'ning turini faqat uning mashqlarida savollar bo'lmaganda o'zgartirish mumkin.

Har bir Part'da **«Mashqdagi savollar soni»** bor (Part sahifasida): yangi mashqning muharriri shuncha
savol qatori bilan ochiladi (Part 5 da 6 ta: 24–29, Part 6 da 6 ta: 30–35). Bo'sh qoldirilsa, turiga qarab
olinadi (A, B, C — 8, eshitib yozish — 6, ro'yxatdan tanlash — 4, xarita — 5). Ortiqcha bo'sh qator
ko'rsatilmaydi; ko'proq savol kerak bo'lsa, «+ Savol qo'shish» tugmasi bor.

`seed_listening_parts` Part 4, 5 va 6 ni shu formatga (hamda ularning umumiy ko'rsatmalari va savollar
soniga) o'tkazadi, lekin faqat hali tahrirlanmagan va savollari yo'q Part'larni: admin o'zgartirgan
Part'larga tegmaydi.

### Mashqni admin paneldan to'ldirish

`/panel/courses/` → kursni **Tahrirlash** → pastdagi **Mashqlar (Practice)** bo'limi:

1. **Part qo'shish** (raqami, nomi, belgisi, turi, birinchi savol raqami, mashqdagi savollar soni,
   umumiy ko'rsatma; ko'rsatmada `**so'z**` qalin bo'ladi). Yangi Part
   uchun savol raqami avvalgi Part'ning oxiridan taklif qilinadi.
   - **Key vocabulary so'zlari:** Part sahifasidagi «Key vocabulary» kartochkasida so'zlar soni va birinchi
     so'zlar ko'rinadi, **➕ So'z qo'shish** (so'z bo'lsa **✏️ So'zlarni tahrirlash**) tugmasi so'zlar sahifasini
     ochadi. U yerda har bir so'z alohida qator: **So'z**, **Talaffuz**, **Ma'no**, **Misol**. Faqat so'z va
     ma'no shart. **+ So'z qo'shish** tugmasi yangi qator qo'shadi; oxirgi maydonda **Enter** bossangiz ham
     yangi qator ochiladi (Enter maydonlar bo'ylab o'tkazadi, formani yubormaydi). **×** so'zni olib tashlaydi
     (**Saqlash** bosilganda o'chadi). Saqlash tugmasi pastda doim ko'rinib turadi. Talaffuzni `/ˈpensl/` yoki
     `ˈpensl` ko'rinishida yozish mumkin: kartochkada o'zi `/…/` ichida chiqadi. Bitta Part'da 300 tagacha so'z.
   - **Ko'p so'zni birdaniga qo'shish:** shu sahifaning pastidagi yopiq «📋 Ko'p so'zni birdaniga qo'shish»
     bo'limiga tayyor ro'yxatni ko'chirib qo'yish mumkin: har qatorga bitta so'z, kartochkada qanday ko'rinsa
     shunday: `so'z /talaffuz/ | o'zbekcha ma'no | misol`. Masalan:
     ```
     pencil /ˈpensl/ | qalam | She borrowed a pencil from her friend.
     student /ˈstjuːdənt/ | talaba, o'quvchi | The new student joined our class.
     water | suv
     ```
     Excel yoki Google Sheets'dan to'rt ustunni (so'z, talaffuz, ma'no, misol) belgilab ko'chirib qo'ysangiz ham
     bo'ladi. «Saqlash» bosilganda bu so'zlar qatorlar ro'yxatining oxiriga qo'shiladi. Xato bo'lsa (masalan,
     ma'no yozilmagan), qator raqami bilan aytiladi va hech narsa saqlanmaydi.
   - Hamma so'zlar olib tashlansa, o'quvchiga tugma ko'rinmaydi. Eski «so'zlar soni» raqami olib tashlangan:
     «50 words» endi haqiqiy so'zlar sonidan hisoblanadi.
2. Part sahifasida **Mashq qo'shish**.
3. Mashq sahifasida **audio fayl** yuklang (mp3, wav, ogg, m4a, aac · 30 MB gacha), davomiylikni
   (daqiqa) kiriting va savollarni qo'shing. Audio va kamida 1 ta savol bo'lsa, mashq **Tayyor** bo'ladi.
   - **Variantlardan tanlash:** har savolda 3 ta variant (A, B, C) va to'g'ri javob; savol matni ixtiyoriy.
   - **Matndagi bo'sh joylar (Reading):** audio kerak emas. «Matn (Passage)» maydoniga katta matnni yozing yoki
     qo'ying va o'quvchi yozishi kerak bo'lgan so'zlarni `[[ikkita kvadrat qavs]]` ichiga oling, masalan
     `Although the [[town]] was small`. O'quvchida u o'rnida «(Q1) 1 [yozish maydoni]» chiqadi; har bir bo'sh joy
     bitta savol bo'lib saqlanadi (saqlagandan keyin «Bo'sh joylar» ro'yxatida ko'rinadi). Bir nechta javob
     qabul qilinsa `[[town / city]]`; abzaslar bo'sh qator bilan ajratiladi (oddiy Enter bo'sh joy sifatida
     o'qiladi, shuning uchun PDF'dan ko'chirilgan matn bir tekis oqadi; bo'sh joydan oldin yozilgan «1.» yoki
     «(Q1)» kabi raqam ikki marta chiqmasligi uchun o'quvchiga ko'rsatilmaydi). Natijalar sahifasida matn
     o'quvchining javoblari va to'g'ri javoblar bilan (`→ town`) qayta chiqadi. Matn va kamida 1 ta bo'sh joy bo'lsa,
     mashq **Tayyor** bo'ladi.
   - **Matn + savollar (Reading Part 4):** «Sarlavha» va «Matn (Passage)» maydonlariga o'qiladigan matnni yozing
     (abzaslar bo'sh qator bilan), savollarni esa «Variantlardan tanlash» kabi kiriting: har birida A, B, C va
     ixtiyoriy D varianti. True / False / Not given savollari uchun A, B, C ga shu so'zlarni yozing. «Oldingi
     sarlavha» maydoniga `**Questions 21-24:** choose the correct answer A, B, C or D.` kabi matn yozsangiz,
     u shu savoldan oldin alohida kartochkada chiqadi.
   - **Matn: bo'sh joylar + test (Reading Part 5):** matnni `[[so'z]]` belgilari bilan yozing (30–33 shu yerdan olinadi),
     pastdagi «Test savollar» qatorlariga 34–35-savollarni (A–D) kiriting. Bo'sh joylar soni o'zgarsa,
     test savollar raqami avtomatik siljiydi. Part sahifasidagi «Mashqdagi savollar soni» bu turda faqat test
     savollar sonini bildiradi (34–35 uchun 2).
   - **Eshitib yozish:** «Sarlavha» maydoniga matn sarlavhasi; har qatorda sarlavha, oldingi/keyingi
     matn va to'g'ri javob(lar). Gapsiz oddiy qator kerak bo'lsa (masalan «Labyrinths represent a journey
     through life.»), uni keyingi qatorning birinchi maydoniga yozing: u shu qatordan oldin alohida satrda
     chiqadi va raqam olmaydi.
   - **Ro'yxatdan tanlash:** «Variantlar ro'yxati» ga har qatorga bittadan variant (harflar avtomatik, 10 tagacha),
     har savol uchun matn (masalan «Speaker 1» yoki butun abzas) va to'g'ri javob harfi. Ixtiyoriy «Sarlavha»
     maydoni variantlar ro'yxati tepasida qalin chiqadi (Headings uchun), savoldagi ixtiyoriy qalin sarlavha esa
     (masalan «Paragraph I») raqam yonida qalin yoziladi, abzas matni uning ostida chiqadi.
   - **Xaritada belgilash:** «Xarita» bo'limida rasm yuklang (png, jpg, gif, webp · 8 MB gacha; A, B, C...
     harflari rasmning o'zida bo'lishi kerak) va «Javob harflari soni»ni kiriting (9 = A–I). Har savol uchun
     joy nomi (masalan «Gift shop») va xaritadagi to'g'ri harf. Audio, rasm, kamida 2 ta harf va 1 ta savol
     bo'lsa, mashq **Tayyor** bo'ladi.
   - **Variantlardan tanlash** savollarida ixtiyoriy «Oldingi sarlavha» maydoni bor: u shu savoldan oldin
     alohida kartochkada chiqadi (Part 5 uchun, masalan `**Extract One** · You hear part of an interview...`).
   - «Shu mashq uchun ko'rsatma» maydoni ixtiyoriy: bo'sh qolsa, Part'ning umumiy ko'rsatmasi chiqadi.
   - **Transcript** (barcha turlarda, ixtiyoriy): audio matni. O'quvchi natijalarni ko'rganda «Transcript»
     bo'limida chiqadi (mashq vaqtida ko'rinmaydi). Abzaslar bo'sh qator bilan ajratiladi; to'g'ri javobli
     joylarni `**ikkita yulduzcha**` ichiga oling — ular sariq rangda ajralib turadi. Bo'sh qoldirilsa,
     Transcript bo'limi chiqmaydi.

Audio va xarita rasmlari `MEDIA_ROOT` da (Docker'da `app_data` volume'ida) saqlanadi va faqat
kirgan foydalanuvchilarga `/courses/audio/<id>/` va `/courses/image/<id>/` orqali beriladi (Range
qo'llab-quvvatlanadi, shuning uchun pleyerda oldinga-orqaga surish ishlaydi). Mashq yoki Part o'chirilsa
(yoki audio/rasm almashtirilsa), eski fayl ham o'chadi.

## Writing (testlar)

**Writing** kursining kartochkasi Part/mashq o'rniga **Writing practice** sahifasini ochadi (`writing/` ilovasi).
Har bir test — haqiqiy imtihon: **Task 1.1**, **Task 1.2** va **Part 2**, jami 60 daqiqa.

1. **Writing practice** — «How to write Task 1.1, 1.2 and Part 2» qo'llanma kartochkasi (**Open the guide**) va
   «Tests · N»: testlar oylar bo'yicha guruhlangan (OCTOBER 2025...), har qatorda sana va smena («18 Oct · 1-smena»),
   test nomi va «Part 2: mavzu». Free/Paid belgisi yo'q; o'quvchi yuborgan testda «✓ Sent» chiqadi.
2. Testni bosganda **intro** (kirish talab qilinadi): «Ready? ⏱ · 3 tasks · 60 minutes in total», topshiriqlar
   ro'yxati va **Start writing 🚀**. Hali topshiriqlari kiritilmagan testda tugma o'chirilgan.
3. **Yozish sahifasi**: tepada Task 1.1 / Task 1.2 / Part 2 tablari (har birida yozilgan so'zlar soni), taymer (60:00),
   **Pause**; Task 1.1 va 1.2 da xat (kichik «kontekst» yozuvi + matn), qalin topshiriq va yozish maydoni.
   **Part 2** da xat yo'q: faqat qalin topshiriq matni («You are participating in an online discussion...») va uning
   tagida oddiy yozuvda «Write 180–200 words.» qatori, so'ng yozish maydoni. **← Previous / Next →** tugmalari va
   **Send to my teacher**.
4. **So'z sanagich**: yozish maydoni ostida «2 words», progress chizig'i va «target about 50 words».
   So'z — bo'shliqsiz belgilar ketma-ketligi (`e-mail`, `don't` — bitta so'z). Maqsad: Task 1.1 — taxminan 50
   (chiziq 45 dan sariqdan yashilga, 60 dan oshsa qizilga o'tadi), Task 1.2 — 120–150, Part 2 — 180–200.
5. **📌 Structure and useful phrases · tap a phrase to add it** (Task 1.1): 6 guruh (Topic, About, Feelings,
   Problem, Suggestions, Ending) × 3 ibora, har biri o'zbekcha tarjimasi bilan. Statik matn (`writing/guides.py`):
   ibora bosilsa, yozish maydonidagi kursor o'rniga qo'shiladi. Namuna javob («👀 Sample answer») admin
   kiritgan bo'lsagina chiqadi.
6. **Send to my teacher** avval ogohlantirish kartochkasini ko'rsatadi (har topshiriq bo'yicha so'zlar soni va
   «Yes, send» / «Keep writing»). Vaqt tugasa, yozilgan matn o'zi yuboriladi. Yuborishdan oldin sahifadan
   chiqilsa, brauzer ogohlantiradi. Yuborilgan ish o'quvchiga «Sent to your teacher» sahifasida nusxa bo'lib
   ko'rinadi; admin uni panelda ko'radi.

**Admin paneldan:** `/panel/courses/` → Writing kursini **Tahrirlash** → **Writing testlar** bo'limi:

- **Test qo'shish** — nomi (masalan «Travel Club»), sana, smena, «Part 2 mavzusi» (ro'yxatda «Part 2: ...» bo'lib
  chiqadi), davomiylik (daqiqa) va 3 ta topshiriq. **Task 1.1 va Task 1.2** da: **Topshiriq** (qalin; shu maydon
  majburiy), **Kontekst** (xat tepasidagi kichik yozuv), **Xat / matn** (xatning o'zi, qator uzilishlari saqlanadi)
  va ixtiyoriy **Namuna javob**. **Part 2** da faqat **Topshiriq** bor: u qalin yoziladi, tagidan «Write 180–200 words.»
  qatori o'zi qo'shiladi (matn oxiriga shu gapni o'zingiz yozsangiz ham ikki marta chiqmaydi); Part 2 da xat,
  kontekst va namuna javob yo'q. Topshiriqning hamma maydonlari bo'sh qolsa, u testda bo'lmaydi.
- **Yuborilgan ishlar** — o'quvchilar yuborgan ishlar (so'zlar soni va yozish vaqti bilan), ishni ochganda har
  topshiriq matni topshirig'i bilan birga ko'rinadi. Hozircha o'qituvchi izohi (feedback) yozish yo'q.
- Testni o'chirsangiz, uning topshiriqlari va o'quvchilar yuborgan ishlar ham o'chadi.

## Speaking (partlar va setlar)

**Speaking** kursining kartochkasi **Speaking practice** sahifasini ochadi (`speaking/` ilovasi):

1. **Speaking practice** — «📊 How you are scored · Baholash tartibi» kartochkasi (Grammar, Vocabulary, Fluency,
   Pronunciation — har biri 25%) va 4 ta part: 💬 Part 1.1 (Questions about you), 🖼️ Part 1.2 (Talk about two pictures),
   🧭 Part 2 (Three questions, one long answer), ⚖️ Part 3 (Discuss both sides of a topic). Har bir kartochkada vaqt
   qatori («3 questions · 5 sec to think · 30 sec to talk») va «✓ 1 / 3 practised» belgisi bor. Free / Full access
   belgilari yo'q.
2. Partni bosganda **Practice questions** ochiladi: Set One, Set Two... — har setda raqamlangan savollar (har
   savol yonidagi 🔊 tugmasi uni brauzer ovozi bilan ingliz tilida o'qib beradi; brauzer ovoz chiqara olmasa, tugma
   ko'rinmaydi) va **🎙️ Practise this** tugmasi (mashq qilingan setda «Practise this again ✓»).
3. **Practise this** → **Ready? 🎙️** sahifasi (kirish talab qilinadi): «3 questions · about 2 minutes»
   (vaqt partning taymerlaridan hisoblanadi), qoidalar, «Read the questions aloud» (tanlov brauzerda eslab
   qolinadi) va **▶ Start**. Hozircha faqat **Part 1.1** boshlanadi; Part 1.2, 2 va 3 uchun Start o'chirilgan.
4. **Mashq** (Start bosilgach shu sahifaning o'zida; brauzer mikrofonga ruxsat so'raydi). Har savol uchun:
   **Listen** (savol ingliz tilida ovoz chiqarib o'qiladi; **Skip →** o'tkazib yuboradi; «Read the questions aloud»
   belgilanmagan bo'lsa, bu bosqich yo'q) → **Prepare** (5 soniya, **Start speaking now →** bilan qisqartirish
   mumkin) → **Speak now** (beep, so'ng 30 soniya; **I'm done →** erta tugatadi; javob yozib olinadi va matnga
   aylantiriladi). Tepada 3 ta segment va «Question 2 of 3 · 2 / 3»; **Stop** ruxsat so'rab to'xtatadi (saqlanmaydi).
5. Oxirgi savoldan keyin javoblar yuboriladi va **natija sahifasi** ochiladi: «🎉 Well done!», coinlar (hamma
   savolda taymer oxirigacha gapirilgan bo'lsa, savollar soniga teng; «I'm done» bosilgan bo'lsa, «No coins this
   time…»), har savol uchun **Your answer** (nima deyilgani, yozib olingan ovoz va necha soniya gapirilgani) va
   **🤖 AI feedback** (qisqa xulosa; Grammar, Vocabulary, Fluency, Pronunciation; «Try saying» — yaxshiroq javob).
   **Try again** va **Back to lesson** tugmalari bor. Mashq tugagach set «practised» bo'ladi.

**AI feedback qanday ishlaydi** (`speaking/ai.py`). Ikki xizmatdan biri ishlatiladi, qaysi biri ekanini `.env` dagi
kalit hal qiladi:

- **Groq — bepul** (karta kerak emas). Yozib olingan ovozni server o'zi **Whisper** bilan matnga aylantiradi
  (har qanday brauzerda ishlaydi, «um», «uh» lar ham yoziladi), so'ng `openai/gpt-oss-120b` modeli shu matnga fikr
  yozadi.
- **Claude — pullik.** Uning kaliti bo'lsa, fikrni Claude yozadi (Groq kaliti ham bo'lsa, ovozni baribir Groq matnga
  aylantiradi).

Til modellari ovozni eshitmaydi: ular matnni (savol, necha soniya gapirilgani va tanib olish aniqligi bilan)
o'qiydi. Shu sababli **talaffuz** faqat tanib olish aniqligi va noto'g'ri eshitilgan so'zlardan taxmin qilinadi.
Groq kaliti bo'lmasa, matnni brauzer tayyorlaydi (`SpeechRecognition`, faqat Chrome / Edge).

**Groq kalitini olish (bepul):** https://console.groq.com ga kiring (Google, GitHub yoki email bilan) →
**API Keys → Create API Key** → nom bering va kalitni (`gsk_...`) nusxalang (u faqat bir marta ko'rsatiladi) →
`.env` ga yozing va `docker compose up -d` qiling (konteyner `.env` ni faqat qayta yaratilganda o'qiydi):

```
GROQ_API_KEY=gsk_...                        # https://console.groq.com → API Keys (bepul)
GROQ_MODEL=openai/gpt-oss-120b              # ixtiyoriy; javobni JSON schema bo'yicha bera oladigan model
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3   # ixtiyoriy: whisper-large-v3-turbo tezroq
ANTHROPIC_API_KEY=sk-ant-...                # ixtiyoriy, pullik: https://console.anthropic.com → API keys
SPEAKING_AI_MODEL=claude-sonnet-5-5         # ixtiyoriy (Claude modeli; arzonrog'i claude-haiku-5-5)
SPEAKING_FEEDBACK_LANGUAGE=English          # ixtiyoriy: masalan Uzbek («Try saying» doim inglizcha)
```

Groq'ning bepul tarifi daqiqasiga va kuniga so'rovlar va tokenlar sonini cheklaydi (o'z limitlaringiz:
console.groq.com → Settings → Limits). Bir vaqtda ko'p o'quvchi tugatsa, ba'zilarida «We could not get the AI
feedback just now» chiqadi — bir ozdan keyin **Get the feedback again** bosiladi. Ovoz yozuvlari va javob matnlari
Groq serverlariga yuboriladi. Claude kaliti uchun console.anthropic.com da **Billing** bo'limida balans
to'ldiriladi (xalqaro Visa / Mastercard kerak), so'ng **API Keys → Create Key**.

Kalit bo'lmasa, mashq va yozib olish baribir ishlaydi; natija sahifasi «The AI feedback is not turned on on this site
yet» deydi va tugma ko'rsatmaydi (adminga kalitni qayerga yozish kerakligi ko'rinadi). Kalit qo'shilgach o'sha eski
natija sahifalarida **Get the feedback** tugmasi paydo bo'ladi: u saqlangan yozuvlarni matnga aylantiradi va fikr
oladi. AI vaqtincha ishlamay qolsa (tarmoq, limit, 529 va h.k.), javoblar saqlanadi va **Get the feedback again**
tugmasi qayta urinadi (adminga xato matni ham ko'rinadi). Mikrofon faqat `http://localhost` yoki
`https://` da ishlaydi (boshqa kompyuter yoki telefondan kirish uchun HTTPS kerak); Groq kaliti bo'lmasa, matnga
aylantirish uchun Chrome yoki Edge kerak (Chrome ovozni Google serveriga yuboradi).

**Mikrofon ruxsati.** «Ready?» sahifasi ochilishi bilan, ruxsat hali berilmagan/rad etilmagan bo'lsa, brauzerning
o'z oynasi (Allow / Block) avtomatik ochiladi; Allow bosilgach sahifada «✓ The microphone is allowed. Press Start
when you are ready.» chiqadi. Start bosilganda ham brauzerdan so'raladi. Sabab turiga qarab aniq xabar chiqadi:
oyna yopilgan («The permission pop-up was closed…»), mikrofon bloklangan (ruxsatni qanday yoqish bosqichlari va
«I allowed it — check again» tugmasi; brauzer sozlamasida ruxsat berilgani o'zi seziladi), mikrofon topilmadi yoki
boshqa dastur band qilgan. Brauzer bloklangan ruxsatni sahifadan qayta so'ray olmaydi — faqat sozlamadan yoqiladi.
Yozib olingan ovozlar `MEDIA_ROOT/speaking/answers/` da saqlanadi va faqat egasiga va adminlarga ko'rinadi;
bir o'quvchi soatiga ko'pi bilan 30 ta mashq qila oladi (AI xarajatini cheklash uchun).

**Admin paneldan:** `/panel/courses/` → Speaking kursini **Tahrirlash** → **Speaking partlar** → part yonidagi
**Boshqarish**. Har set uchun savollarni har qatorga bittadan yozing (odatda 3 ta, ko'pi bilan 12 ta). Yangi set
qo'shish uchun pastdagi bo'sh «Yangi set» maydonini to'ldiring: raqami o'zi qo'yiladi (Set One, Set Two...).
«Setni o'chirish» belgilanib saqlansa, set o'chadi; savollari butunlay o'chirilgan set qoladi, lekin o'quvchiga
ko'rinmaydi. Partlarning nomi, tavsifi va vaqt qatorlari kodda (`speaking/models.py`, `PART_RULES`).
