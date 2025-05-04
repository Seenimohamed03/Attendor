from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student_id = models.CharField(max_length=20, unique=True)
    roll_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    class_section = models.CharField(max_length=50)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    emergency_contact = models.CharField(max_length=100, null=True, blank=True)
    parent_phone = models.CharField(max_length=15, null=True, blank=True, verbose_name="Parent's Phone Number")
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    leave_request_notifications = models.BooleanField(default=True)
    news_notifications = models.BooleanField(default=True)
    
    # Privacy Settings
    show_profile = models.BooleanField(default=True)
    show_attendance = models.BooleanField(default=False)
    show_contact = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"

    def get_full_name(self):
        return self.user.get_full_name()

    def get_email(self):
        return self.user.email

    def get_attendance_percentage(self):
        total_days = Attendance.objects.filter(student=self).count()
        if total_days == 0:
            return 0
        present_days = Attendance.objects.filter(student=self, status=True).count()
        return round((present_days / total_days) * 100, 2)

    def get_recent_attendance(self, limit=5):
        return Attendance.objects.filter(student=self).order_by('-date')[:limit]

    def get_recent_leave_requests(self, limit=5):
        return LeaveRequest.objects.filter(student=self).order_by('-created_at')[:limit]

class Attendance(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    status = models.BooleanField(default=False)  # False for absent, True for present
    marked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='marked_attendances')
    edited = models.BooleanField(default=False)  # Track if attendance has been edited
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='edited_attendances')
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['student', 'date']

class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField()
    document = models.FileField(upload_to='leave_documents/', null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class News(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='news_images/', null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='posted_news')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('ATTENDANCE', 'Attendance Alert'),
        ('LEAVE', 'Leave Request Update'),
        ('NEWS', 'News Update'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
