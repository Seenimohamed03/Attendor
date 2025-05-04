from django.contrib import admin
from .models import StudentProfile, Attendance, LeaveRequest, News, Notification

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'user', 'get_roll_number', 'class_section', 'get_attendance_percentage')
    search_fields = ('student_id', 'user__username', 'user__first_name', 'user__last_name')
    list_filter = ('class_section',)
    
    def get_roll_number(self, obj):
        return obj.student_id
    get_roll_number.short_description = 'Roll Number'
    
    def get_attendance_percentage(self, obj):
        return f"{obj.get_attendance_percentage()}%"
    get_attendance_percentage.short_description = 'Attendance %'

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'status', 'marked_by')
    list_filter = ('status', 'date')
    search_fields = ('student__student_id', 'student__user__username')

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'from_date', 'to_date', 'status')
    list_filter = ('status', 'from_date', 'to_date')
    search_fields = ('student__student_id', 'student__user__username')

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at', 'updated_at')
    search_fields = ('title', 'description')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'title')
