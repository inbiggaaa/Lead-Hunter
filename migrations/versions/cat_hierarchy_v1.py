"""Add categories table, restructure segments into category→subcategory hierarchy.

Categories: 16 | Subcategories: 66

Revision ID: cat_hierarchy_v1
Revises: focus_countries
Create Date: 2026-07-08
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "cat_hierarchy_v1"
down_revision: Union[str, None] = "focus_countries"
branch_labels: Union[dict[str, str], None] = None
depends_on: Union[list[str], None] = None

# ── Category + Subcategory data ──

CATEGORIES = [
    (1,  "transport",       "🚗", "Транспорт",                 "Transport"),
    (2,  "logistics",       "📦", "Логистика",                 "Logistics"),
    (3,  "real-estate",     "🏠", "Недвижимость",              "Real Estate"),
    (4,  "beauty",          "💆", "Красота и уход",            "Beauty & Care"),
    (5,  "doctor",          "🩺", "Врач",                      "Doctor"),
    (6,  "translator",      "🗣️", "Переводчик",               "Translator"),
    (7,  "education",       "📚", "Обучение и курсы",          "Education"),
    (8,  "home",            "🧹", "Дом и быт",                 "Home & Household"),
    (9,  "tourism",         "✈️", "Туризм",                    "Tourism"),
    (10, "catering",        "🍽️", "Кейтеринг и мероприятия",  "Catering & Events"),
    (11, "fitness",         "🏋️", "Фитнес и спорт",            "Fitness & Sports"),
    (12, "media-design",    "📸", "Медиа и дизайн",            "Media & Design"),
    (13, "legal",           "⚖️", "Консультация и Право",      "Legal & Consulting"),
    (14, "finance",         "💰", "Финансы",                   "Finance"),
]

# (cat_slug, slug, emoji, title_ru, title_en, sort)
SEGMENTS = [
    # ── 1. transport ──
    ("transport", "scooter-rental",   "🛵", "Аренда скутеров и мотоциклов", "Scooter & motorcycle rental", 1),
    ("transport", "car-rental",       "🚙", "Аренда автомобиля",            "Car rental",                  2),
    ("transport", "moto-purchase",    "🏍️", "Покупка мотоцикла",           "Motorcycle purchase",         3),
    ("transport", "car-purchase",     "🚘", "Покупка авто",                 "Car purchase",                4),
    # ── 2. logistics ──
    ("logistics", "delivery",         "🚚", "Доставка",                     "Delivery",                    1),
    ("logistics", "courier",          "🛵", "Курьер",                       "Courier",                     2),
    ("logistics", "cargo",            "📦", "Грузоперевозки",               "Cargo transportation",        3),
    # ── 3. real-estate ──
    ("real-estate", "housing-rent",   "🏠", "Аренда жилья",                 "Housing rental",              1),
    ("real-estate", "housing-buy",    "🏡", "Покупка жилья",                "Housing purchase",            2),
    # ── 4. beauty ──
    ("beauty", "massage",             "💆", "Массаж",                       "Massage",                     1),
    ("beauty", "manicure",            "💅", "Маникюр / Педикюр",            "Manicure / Pedicure",         2),
    ("beauty", "cosmetology",         "🧖", "Косметолог",                  "Cosmetology",                 3),
    ("beauty", "hairdresser",         "💇", "Парикмахер",                  "Hairdresser",                 4),
    ("beauty", "hair-color",          "🎨", "Покраска и колорирование",     "Hair coloring",               5),
    ("beauty", "tattoo",              "🖊️", "Татуировки",                  "Tattoo",                      6),
    ("beauty", "lashes",              "👁️", "Ресницы",                     "Lashes",                      7),
    ("beauty", "brows",               "✏️", "Брови",                       "Brows",                       8),
    ("beauty", "makeup",              "💄", "Визажист",                    "Makeup artist",               9),
    ("beauty", "barber",              "💈", "Барбер",                      "Barber",                     10),
    ("beauty", "epilation",           "✨", "Эпиляция",                    "Epilation",                  11),
    # ── 5. doctor ──
    ("doctor", "therapist",           "🩺", "Терапевт",                    "Therapist",                   1),
    ("doctor", "dentist",             "🦷", "Стоматолог",                  "Dentist",                     2),
    ("doctor", "psychologist",        "🧠", "Психолог",                    "Psychologist",                3),
    ("doctor", "dermatologist",       "🔬", "Дерматолог",                  "Dermatologist",               4),
    ("doctor", "gynecologist",        "👩‍⚕️", "Гинеколог",                   "Gynecologist",                5),
    ("doctor", "pediatrician",        "👶", "Педиатр",                     "Pediatrician",                6),
    ("doctor", "surgeon",             "🏥", "Хирург",                      "Surgeon",                     7),
    ("doctor", "orthopedist",         "🦴", "Ортопед",                     "Orthopedist",                 8),
    ("doctor", "neurologist",         "🧬", "Невролог",                    "Neurologist",                 9),
    ("doctor", "nutritionist",        "🥗", "Нутрициолог",                 "Nutritionist",               10),
    # ── 6. translator ──
    ("translator", "translator",      "🗣️", "Переводчик",                  "Translator",                  1),
    # ── 7. education ──
    ("education", "language-courses", "🌐", "Курсы иностранных языков",    "Language courses",            1),
    ("education", "driving-instructor","🚗", "Автоинструктор",             "Driving instructor",          2),
    ("education", "moto-instructor",  "🏍️", "Мотоинструктор",             "Moto instructor",             3),
    ("education", "tutor",            "📝", "Репетитор",                   "Tutor",                       4),
    # ── 8. home ──
    ("home", "cleaning",              "🧹", "Клининг",                     "Cleaning",                    1),
    ("home", "repair",                "🔨", "Ремонт и отделка",            "Repair & renovation",         2),
    ("home", "plumber",               "🔧", "Сантехник",                   "Plumber",                     3),
    ("home", "electrician",           "⚡", "Электрик",                    "Electrician",                 4),
    ("home", "nanny",                 "👶", "Няни и присмотр",             "Nanny & babysitting",         5),
    ("home", "pets",                  "🐾", "Услуги для животных",         "Pet services",                6),
    # ── 9. tourism ──
    ("tourism", "guide",              "🗺️", "Гид",                         "Guide",                       1),
    ("tourism", "excursions",         "🏖️", "Экскурсии",                   "Excursions",                  2),
    ("tourism", "visa-support",       "🛂", "Визовая поддержка",           "Visa support",                3),
    ("tourism", "travel-agent",       "✈️", "Туристический агент",         "Travel agent",                4),
    ("tourism", "taxi-transfer",      "🚕", "Такси / Трансфер",            "Taxi / Transfer",             5),
    ("tourism", "driver",             "🚗", "Водитель с авто",             "Driver with car",             6),
    # ── 10. catering ──
    ("catering", "catering",          "🍽️", "Кейтеринг",                   "Catering",                    1),
    ("catering", "private-chef",      "👨‍🍳", "Повар на дом",               "Private chef",                2),
    ("catering", "pastry-chef",       "🍰", "Кондитер",                    "Pastry chef",                 3),
    ("catering", "event-management",  "🎉", "Организация мероприятий",     "Event management",            4),
    ("catering", "music",             "🎵", "Музыкальное сопровождение",   "Music accompaniment",         5),
    # ── 11. fitness ──
    ("fitness", "fitness",            "💪", "Фитнес",                      "Fitness",                     1),
    ("fitness", "yoga",               "🧘", "Йога",                        "Yoga",                        2),
    ("fitness", "martial-arts",       "🥋", "Единоборства",                "Martial arts",                3),
    ("fitness", "pilates",            "🤸", "Пилатес",                     "Pilates",                     4),
    ("fitness", "padel",              "🎾", "Падел",                       "Padel",                       5),
    ("fitness", "tennis",             "🎾", "Теннис",                      "Tennis",                      6),
    ("fitness", "basketball",         "🏀", "Баскетбол",                   "Basketball",                  7),
    ("fitness", "football",           "⚽", "Футбол",                      "Football",                    8),
    # ── 12. media-design ──
    ("media-design", "photo",         "📷", "Фото",                        "Photography",                 1),
    ("media-design", "video",         "🎬", "Видео",                       "Videography",                 2),
    ("media-design", "design",        "🎨", "Дизайн",                      "Design",                      3),
    ("media-design", "graphics",      "🖼️", "Графика",                    "Graphics",                    4),
    # ── 13. legal ──
    ("legal", "notary",               "📜", "Нотариус",                    "Notary",                      1),
    ("legal", "company-registration", "🏢", "Открытие компании",           "Company registration",        2),
    ("legal", "lawyer",               "⚖️", "Адвокат",                     "Lawyer",                      3),
    ("legal", "accountant",           "📊", "Бухгалтер",                   "Accountant",                  4),
    # ── 14. finance ──
    ("finance", "currency-exchange",  "💱", "Обмен валют",                 "Currency exchange",           1),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create categories table
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("title_ru", sa.Text(), nullable=True),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("emoji", sa.String(8), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # 2. Insert categories
    for cat_id, slug, emoji, title_ru, title_en in CATEGORIES:
        conn.execute(
            sa.text(
                "INSERT INTO categories (id, slug, emoji, title_ru, title_en, sort_order, is_active) "
                "VALUES (:id, :slug, :emoji, :title_ru, :title_en, :sort, true)"
            ),
            {"id": cat_id, "slug": slug, "emoji": emoji, "title_ru": title_ru, "title_en": title_en, "sort": cat_id},
        )

    # 3. Add category_id to segments (sort_order already exists)
    op.add_column("segments", sa.Column("category_id", sa.BigInteger(), nullable=True))

    op.create_foreign_key(
        "fk_segments_category_id", "segments", "categories",
        ["category_id"], ["id"], ondelete="RESTRICT",
    )

    # 4. Delete old keyword data
    op.execute(sa.text("DELETE FROM segment_keywords"))

    # 5. Delete old channel_segments
    op.execute(sa.text("DELETE FROM channel_segments"))

    # 6. Delete old segments and user_subscriptions referencing them
    #    user_subscriptions has ON DELETE CASCADE, but let's be explicit
    op.execute(sa.text("DELETE FROM user_subscriptions"))
    op.execute(sa.text("DELETE FROM segments"))

    # 7. Insert new segments with category_id
    cat_id_map = {slug: cat_id for cat_id, slug, _, _, _ in CATEGORIES}
    for cat_slug, seg_slug, emoji, title_ru, title_en, sort in SEGMENTS:
        cid = cat_id_map[cat_slug]
        conn.execute(
            sa.text(
                "INSERT INTO segments (category_id, slug, emoji, title_ru, title_en, sort_order, is_active) "
                "VALUES (:cid, :slug, :emoji, :title_ru, :title_en, :sort, true)"
            ),
            {"cid": cid, "slug": seg_slug, "emoji": emoji, "title_ru": title_ru, "title_en": title_en, "sort": sort},
        )

    # 8. Make category_id NOT NULL after data is in place
    op.alter_column("segments", "category_id", nullable=False, existing_type=sa.BigInteger())

    # 9. Reset sequence for categories (since we inserted with explicit IDs)
    conn.execute(sa.text("SELECT setval('categories_id_seq', 14, true)"))

    print(f"  Created 14 categories, {len(SEGMENTS)} subcategories")


def downgrade() -> None:
    """Revert schema (data loss is irreversible)."""
    op.drop_constraint("fk_segments_category_id", "segments", type_="foreignkey")
    op.drop_column("segments", "category_id")
    op.drop_table("categories")
