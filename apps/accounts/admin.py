"""
Accounts admin — Organization, User (Agent), Contact.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import Organization, User, Contact


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'plan', 'is_active', 'user_count', 'created_at']
    list_filter = ['plan', 'is_active', 'country']
    search_fields = ['name', 'slug']
    readonly_fields = ['id', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('name',)}

    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Agents'


@admin.register(User)
class AgentAdmin(UserAdmin):
    list_display = ['email', 'nombre', 'apellido', 'rol', 'organization', 'is_active', 'last_seen']
    list_filter = ['rol', 'is_active', 'organization']
    search_fields = ['email', 'nombre', 'apellido']
    ordering = ['email']
    readonly_fields = ['id', 'last_seen', 'created_at', 'updated_at']

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Personal Info', {'fields': ('nombre', 'apellido', 'telefono', 'avatar')}),
        ('Organization & Role', {'fields': ('organization', 'rol')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Activity', {'fields': ('last_seen', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nombre', 'apellido', 'organization', 'rol', 'password1', 'password2'),
        }),
    )


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'apellido', 'telefono', 'email', 'tipo', 'organization', 'created_at']
    list_filter = ['tipo', 'organization', 'is_active']
    search_fields = ['nombre', 'apellido', 'email', 'telefono', 'cedula']
    readonly_fields = ['id', 'created_at', 'updated_at']
