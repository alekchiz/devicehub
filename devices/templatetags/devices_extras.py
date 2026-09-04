from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Возвращает значение словаря по ключу (для доступа к repair_map в шаблоне)."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None
