
from django.db import migrations


INITIAL_SKILLS = [
    ("copywriting", "Copywriting"),
    ("graphic-design", "Graphic Design"),
    ("video-editing", "Video Editing"),
    ("video-production", "Video Production"),
    ("social-media-management", "Social Media Management"),
    ("paid-advertising", "Paid Advertising"),
    ("email-marketing", "Email Marketing"),
    ("marketing-strategy", "Marketing Strategy"),
    ("photography", "Photography"),
    ("seo", "SEO"),
    ("analytics", "Analytics"),
]


def populate_skills(apps, schema_editor):
    Skill = apps.get_model("organization", "Skill")

    for code, name in INITIAL_SKILLS:
        Skill.objects.using(schema_editor.connection.alias).get_or_create(
            code=code,
            defaults={"name": name},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0003_skill_workspacememberskill"),
    ]

    operations = [
        migrations.RunPython(
            populate_skills,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
