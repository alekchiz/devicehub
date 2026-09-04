"""Заявки: реэкспорт для обратной совместимости (логика разбита по модулям)."""
from .tickets_common import (
    format_ticket_message, menu_keyboard,
    get_profile, find_device, create_ticket, get_my_tickets, get_all_tickets,
    get_admins, get_ticket, search_tickets, update_ticket, can_edit_ticket,
    get_device_full,
    TICKET_PAK, TICKET_PROBLEM, TICKET_NAME, TICKET_PHONE, SEARCH_QUERY,
    EDIT_TICKET_SELECT, EDIT_TICKET_FIELD, EDIT_TICKET_PROBLEM,
    EDIT_TICKET_NAME, EDIT_TICKET_PHONE, STATUS_HOSTNAME,
)
from .tickets_create import (
    ticket_create_start, ticket_pak_handler, ticket_problem_handler,
    ticket_name_handler, ticket_phone_handler,
)
from .tickets_list import my_tickets_handler, all_tickets_handler, ticket_detail_handler
from .tickets_search import search_start, search_result
from .tickets_edit import (
    edit_ticket_start, edit_ticket_select, edit_field_handler,
    edit_problem_handler, edit_name_handler, edit_phone_handler,
)
from .tickets_status import status_start, status_result