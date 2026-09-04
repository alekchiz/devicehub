from django.contrib import admin
from .models import Ticket, TicketComment, ActivityLog

class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 0

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'device', 'status', 'created_by', 'assigned_to', 'created_at')
    list_filter = ('status', 'assigned_to')
    search_fields = ('device__hostname', 'problem', 'contact_name')
    inlines = [TicketCommentInline]
    autocomplete_fields = ('device',)
    list_select_related = ('device', 'created_by', 'assigned_to')
    list_per_page = 25

@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'user', 'created_at')

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'object_id', 'created_at')
    list_filter = ('action', 'model_name')
    search_fields = ('description', 'user__username')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'description', 'created_at')

    # Журнал — только для чтения.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
