"""The "Structure and useful phrases" shown under a writing task: the same for every test, so written down here.

Each group is a step of the e-mail (its name, a hint in Uzbek) with phrases as (English with ____ blanks, Uzbek).
"""

INFORMAL_EMAIL = [
    {
        'title': 'Topic',
        'hint': "nima mazmunida kimdan xabar olganingiz",
        'phrases': [
            ('I just received an e-mail about ____ from ____.',
             'Men xozirgina ____ dan ____ xaqida e-mail oldim.'),
            ('I just got a message regarding ____ from ____.',
             'Men xozirgina ____ yuzasidan ____ dan xabar oldim.'),
            ('I was wondering if you received the e-mail about ____ from ____.',
             "Siz ____ haqida ____dan kelgan elektron xatni olganmisiz, deb so'ramoqchi edim."),
        ],
    },
    {
        'title': 'About',
        'hint': "xatda nimalar aytilgani va so'ralgani",
        'phrases': [
            ('____ asked me to give some suggestions about ____.',
             "____ mendan ____ xaqida tavsiyalar berishimni so'radi."),
            ('I was asked about my thoughts regarding ____.',
             "Mendan ____ yuzasidan fikrlarim so'raldi."),
            ('____ wanted me to share my opinions about ____.',
             "____ meni ____ xaqida fikrlarimni bo'lishishni xohladi."),
        ],
    },
    {
        'title': 'Feelings',
        'hint': "xatdan keyin o'zingizni qanday his qildingiz",
        'phrases': [
            ('I am really glad to receive this message as you know how much I love ____.',
             "Men bu xabarni olganimdan juda ham mamnunman, chunki bilasan ____ ni qanchalik yoqtirishimni."),
            ('I am happy to get this message since the message shows how much ____ care about us.',
             "Men bu xabarni olganimdan xursandman, chunki bu xabar ____ biz xaqimizda qanchalik qayg'urushlarini ko'rsatadi."),
            ('I appreciate their message as they truly care about their ____.',
             "Men bu xabarni juda qadrlayman, chunki ular o'zlarining ____ xaqida rostdan qayg'urishar ekan."),
        ],
    },
    {
        'title': 'Problem',
        'hint': "agar biror muammo bo'lsa",
        'phrases': [
            ('I am a little concerned about ____ because it may cause some problems.',
             "Men ____ haqida biroz xavotirdaman, chunki bu ba'zi muammolarni keltirib chiqarishi mumkin."),
            ('I am worried that ____ could create difficulties for us.',
             "Men ____ biz uchun qiyinchiliklar tug'dirishidan xavotirdaman."),
            ('I am not really happy about this change as it may cause some inconvenience.',
             "Men bu o'zgarishdan unchalik xursand emasman, chunki bu ba'zi noqulayliklarni keltirib chiqarishi mumkin."),
        ],
    },
    {
        'title': 'Suggestions',
        'hint': "mavzu yuzasidan takliflaringiz",
        'phrases': [
            ('I think it would be a good idea to ____ because it could make things better.',
             "Menimcha, ____ yaxshi fikr bo'lardi, chunki bu vaziyatni yaxshilashi mumkin."),
            ('I would suggest ____ as it could be a great way to solve this problem.',
             "Men ____ni taklif qilgan bo'lardim, chunki bu muammoni hal qilishning ajoyib usuli bo'lishi mumkin."),
            ('Perhaps we could ____ so that everyone would benefit from it.',
             "Balki, hamma bundan foyda ko'rishi uchun ____ qilishimiz mumkin."),
        ],
    },
    {
        'title': 'Ending',
        'hint': "e-mailni yakunlash",
        'phrases': [
            ('I hope they will consider my suggestions and make the right decision.',
             "Umid qilamanki, ular mening takliflarimni inobatga olib, to'g'ri qaror qabul qilishadi."),
            ('Anyway, I hope everything goes well and I look forward to hearing from you soon.',
             "Har holda, hammasi yaxshi bo'lishiga umid qilaman va sizdan tez orada xabar kutaman."),
            ("I'm sure they will take our opinions into consideration and make some positive changes.",
             "Ishonchim komilki, ular bizning fikrlarimizni inobatga olib, ijobiy o'zgarishlar qilishadi."),
        ],
    },
]
