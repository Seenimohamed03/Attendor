from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count, Sum
from django.utils import timezone
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import io
from .models import StudentProfile, Attendance, LeaveRequest, News, Notification, User
from .forms import (
    StudentRegistrationForm, AttendanceUploadForm, AttendanceMarkForm,
    LeaveRequestForm, NewsForm, DateRangeForm, StudentProfileUpdateForm, UserUpdateForm, StudentProfileForm
)
from django.contrib.auth import authenticate
import base64
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.conf import settings
import json
from django.urls import reverse

def is_admin(user):
    return user.is_authenticated and user.is_staff

def is_student(user):
    return user.is_authenticated and hasattr(user, 'student_profile')

# Admin Views
@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    # Get total counts
    total_students = StudentProfile.objects.count()
    total_attendance = Attendance.objects.count()
    total_leave_requests = LeaveRequest.objects.count()
    total_news = News.objects.count()
    
    # Get today's attendance
    today = timezone.now().date()
    present_count = Attendance.objects.filter(date=today, status=True).count()
    absent_count = Attendance.objects.filter(date=today, status=False).count()
    
    # Get pending leave requests
    pending_leave_requests = LeaveRequest.objects.filter(status='PENDING').order_by('-created_at')[:5]
    
    # Calculate low attendance students
    low_attendance_students = 0
    for student in StudentProfile.objects.all():
        if student.get_attendance_percentage() < 75:
            low_attendance_students += 1
    
    # Get recent activities
    recent_attendance = []
    dates = Attendance.objects.dates('date', 'day', order='DESC')[:5]
    for date in dates:
        present = Attendance.objects.filter(date=date, status=True).count()
        absent = Attendance.objects.filter(date=date, status=False).count()
        recent_attendance.append({
            'date': date,
            'present_count': present,
            'absent_count': absent,
            'class_section': 'All Classes'
        })
    
    # Get recent news
    recent_news = News.objects.order_by('-created_at')[:5]
    
    context = {
        'total_students': total_students,
        'total_attendance': total_attendance,
        'total_leave_requests': total_leave_requests,
        'total_news': total_news,
        'present_count': present_count,
        'absent_count': absent_count,
        'pending_requests': pending_leave_requests.count(),
        'pending_leave_requests': pending_leave_requests,
        'low_attendance_students': low_attendance_students,
        'recent_attendance': recent_attendance,
        'recent_news': recent_news,
    }
    
    return render(request, 'attendance_core/admin/dashboard.html', context)

@login_required
@user_passes_test(is_admin)
def student_management(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()  # This already creates the StudentProfile with proper student_id
            messages.success(request, 'Student added successfully')
            return redirect('student_management')
    else:
        form = StudentRegistrationForm()

    students = StudentProfile.objects.all()
    return render(request, 'attendance_core/admin/student_management.html', {
        'form': form,
        'students': students
    })

@login_required
@user_passes_test(is_admin)
def mark_attendance(request):
    if request.method == 'POST':
        try:
            if request.headers.get('Content-Type') == 'application/json':
                data = json.loads(request.body)
                date = data.get('date')
                student_ids = data.get('student_ids', [])
                status = data.get('status')
                reset = data.get('reset', False)
            else:
                date = request.POST.get('date')
                student_ids = request.POST.getlist('selected_students[]')
                status = False  # Default to absent for form submissions
                reset = request.POST.get('reset', False)
            
            # Handle reset request
            if reset:
                # Delete all attendance records for today
                today = timezone.now().date()
                Attendance.objects.filter(date=today).delete()
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': True,
                        'message': 'Today\'s attendance record has been reset.',
                        'present_count': 0,
                        'absent_count': 0,
                        'present_students': [],
                        'absent_students': []
                    })
                messages.success(request, 'Today\'s attendance record has been reset.')
                return redirect('mark_attendance')
            
            # Check if attendance is already marked for this date
            existing_attendance = Attendance.objects.filter(date=date, edited=True).exists()
            if existing_attendance:
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'message': 'Attendance has already been marked for this date and cannot be changed.'
                    })
                messages.warning(request, 'Attendance has already been marked for this date and cannot be changed.')
                return redirect('mark_attendance')
            
            # Mark selected students as absent
            for student_id in student_ids:
                try:
                    student = StudentProfile.objects.get(id=student_id)
                    attendance, created = Attendance.objects.get_or_create(
                        student=student,
                        date=date,
                        defaults={
                            'status': status,
                            'marked_by': request.user,
                            'edited': True,
                            'edited_by': request.user,
                            'edited_at': timezone.now()
                        }
                    )
                    
                    if not created and not attendance.edited:
                        attendance.status = status
                        attendance.marked_by = request.user
                        attendance.edited = True
                        attendance.edited_by = request.user
                        attendance.edited_at = timezone.now()
                        attendance.save()
                except StudentProfile.DoesNotExist:
                    if request.headers.get('Content-Type') == 'application/json':
                        return JsonResponse({
                            'success': False,
                            'message': f'Student with ID {student_id} not found.'
                        })
                    messages.error(request, f'Student with ID {student_id} not found.')
                    return redirect('mark_attendance')
            
            # Get updated counts and student lists
            present_students = StudentProfile.objects.filter(
                attendance__date=date,
                attendance__status=True,
                attendance__edited=True
            ).distinct()
            
            absent_students = StudentProfile.objects.filter(
                attendance__date=date,
                attendance__status=False,
                attendance__edited=True
            ).distinct()
            
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': 'Attendance marked successfully',
                    'present_count': present_students.count(),
                    'absent_count': absent_students.count(),
                    'present_students': [
                        {
                            'id': student.id,
                            'name': student.user.get_full_name(),
                            'student_id': student.student_id,
                            'class_section': student.class_section,
                            'profile_picture': student.profile_picture.url if student.profile_picture else None
                        } for student in present_students
                    ],
                    'absent_students': [
                        {
                            'id': student.id,
                            'name': student.user.get_full_name(),
                            'student_id': student.student_id,
                            'class_section': student.class_section,
                            'profile_picture': student.profile_picture.url if student.profile_picture else None
                        } for student in absent_students
                    ]
                })
            
            messages.success(request, 'Attendance has been marked successfully.')
            return redirect('mark_attendance')
            
        except Exception as e:
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=400)
            messages.error(request, f'Error marking attendance: {str(e)}')
            return redirect('mark_attendance')
    
    today = timezone.now().date()
    students = StudentProfile.objects.all()
    class_sections = StudentProfile.objects.values_list('class_section', flat=True).distinct()
    
    # Get attendance for today
    today_attendance = {}
    for student in students:
        attendance = Attendance.objects.filter(student=student, date=today).first()
        today_attendance[student.id] = attendance
    
    # Get present and absent students for today
    present_students = StudentProfile.objects.filter(
        attendance__date=today,
        attendance__status=True,
        attendance__edited=True
    ).distinct()
    
    absent_students = StudentProfile.objects.filter(
        attendance__date=today,
        attendance__status=False,
        attendance__edited=True
    ).distinct()
    
    context = {
        'students': students,
        'today': today,
        'today_attendance': today_attendance,
        'class_sections': class_sections,
        'present_students': present_students,
        'absent_students': absent_students,
        'is_attendance_marked': Attendance.objects.filter(date=today, edited=True).exists()
    }
    
    return render(request, 'attendance_core/admin/mark_attendance.html', context)

@login_required
@user_passes_test(is_admin)
def export_attendance(request):
    # Get date from request and convert to date object
    date_str = request.GET.get('date')
    if date_str:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date = timezone.now().date()
    else:
        date = timezone.now().date()
    
    # Get all students and their attendance for the specified date
    students = StudentProfile.objects.all().order_by('class_section', 'user__first_name')
    attendance_data = []
    
    for student in students:
        try:
            attendance = Attendance.objects.get(student=student, date=date)
            status = 'Present' if attendance.status else 'Absent'
        except Attendance.DoesNotExist:
            status = 'Not Marked'
            
        attendance_data.append({
            'Student ID': student.student_id,
            'Name': f"{student.user.first_name} {student.user.last_name}",
            'Class': student.class_section,
            'Status': status,
            'Date': date.strftime('%Y-%m-%d')
        })
    
    # Create DataFrame
    df = pd.DataFrame(attendance_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
    
    # Prepare response
    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=attendance_{date}.xlsx'
    
    return response

@login_required
@user_passes_test(is_admin)
def attendance_analytics(request):
    form = DateRangeForm(request.GET)
    start_date = timezone.now().date() - timedelta(days=30)
    end_date = timezone.now().date()
    class_section = None

    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        class_section = form.cleaned_data['class_section']

    students = StudentProfile.objects.all()
    if class_section:
        students = students.filter(class_section=class_section)

    attendance_data = []
    total_present_days = 0
    total_days = 0
    daily_attendance = {}
    class_wise_stats = {}
    month_wise_stats = {}

    # Calculate daily attendance
    current_date = start_date
    while current_date <= end_date:
        daily_present = Attendance.objects.filter(
            date=current_date,
            status=True
        ).count()
        daily_total = Attendance.objects.filter(date=current_date).count()
        daily_attendance[current_date] = {
            'present': daily_present,
            'total': daily_total,
            'percentage': (daily_present / daily_total * 100) if daily_total > 0 else 0
        }
        current_date += timedelta(days=1)

    # Calculate class-wise statistics
    for student in students:
        class_section = student.class_section
        if class_section not in class_wise_stats:
            class_wise_stats[class_section] = {
                'total_students': 0,
                'total_days': 0,
                'total_present': 0
            }
        class_wise_stats[class_section]['total_students'] += 1
        class_wise_stats[class_section]['total_days'] += Attendance.objects.filter(
            student=student,
            date__range=[start_date, end_date]
        ).count()
        class_wise_stats[class_section]['total_present'] += Attendance.objects.filter(
            student=student,
            date__range=[start_date, end_date],
            status=True
        ).count()

    # Calculate month-wise statistics
    current_month = start_date.replace(day=1)
    while current_month <= end_date:
        month_end = (current_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        month_present = Attendance.objects.filter(
            date__range=[current_month, month_end],
            status=True
        ).count()
        month_total = Attendance.objects.filter(
            date__range=[current_month, month_end]
        ).count()
        month_wise_stats[current_month.strftime('%B %Y')] = {
            'present': month_present,
            'total': month_total,
            'percentage': (month_present / month_total * 100) if month_total > 0 else 0
        }
        current_month = (current_month + timedelta(days=32)).replace(day=1)

    for student in students:
        student_total_days = Attendance.objects.filter(
            student=student,
            date__range=[start_date, end_date]
        ).count()
        student_present_days = Attendance.objects.filter(
            student=student,
            date__range=[start_date, end_date],
            status=True
        ).count()
        percentage = (student_present_days / student_total_days * 100) if student_total_days > 0 else 0
        
        total_present_days += student_present_days
        total_days += student_total_days
        
        attendance_data.append({
            'student': student,
            'percentage': percentage,
            'present_days': student_present_days,
            'total_days': student_total_days
        })

    # Sort attendance data by percentage
    attendance_data.sort(key=lambda x: x['percentage'])

    return render(request, 'attendance_core/admin/attendance_analytics.html', {
        'form': form,
        'attendance_data': attendance_data,
        'total_present_days': total_present_days,
        'total_days': total_days,
        'daily_attendance': daily_attendance,
        'class_wise_stats': class_wise_stats,
        'month_wise_stats': month_wise_stats,
        'start_date': start_date,
        'end_date': end_date
    })

@login_required
@user_passes_test(is_admin)
def manage_news(request):
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES)
        if form.is_valid():
            news = form.save(commit=False)
            news.posted_by = request.user
            news.save()
            
            # Check if notifications should be sent
            notify_students = request.POST.get('notify_students', 'false') == 'true'
            if notify_students:
                # Get all students
                students = User.objects.filter(student_profile__isnull=False)
                
                # Create notifications for all students
                for student in students:
                    Notification.objects.create(
                        user=student,
                        title='New Announcement',
                        message=f'New announcement: {news.title}',
                        type='NEWS'
                    )
            
            messages.success(request, 'News posted successfully!')
            return redirect('manage_news')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = NewsForm()
    
    # Get news statistics
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    
    total_news = News.objects.count()
    news_this_month = News.objects.filter(created_at__gte=start_of_month).count()
    news_today = News.objects.filter(created_at__date=today).count()
    
    # Get all news ordered by creation date
    news_list = News.objects.all().order_by('-created_at')
    
    return render(request, 'attendance_core/admin/manage_news.html', {
        'form': form,
        'news_list': news_list,
        'total_news': total_news,
        'news_this_month': news_this_month,
        'news_today': news_today
    })

@login_required
@user_passes_test(is_admin)
def manage_leave_requests(request):
    if request.method == 'POST':
        leave_id = request.POST.get('leave_id')
        action = request.POST.get('action')
        leave_request = get_object_or_404(LeaveRequest, id=leave_id)
        
        if action in ['APPROVED', 'REJECTED']:
            leave_request.status = action
            leave_request.save()
            
            # Create notification for student
            Notification.objects.create(
                user=leave_request.student.user,
                type='LEAVE',
                title='Leave Request Update',
                message=f'Your leave request from {leave_request.from_date} to {leave_request.to_date} has been {action.lower()}'
            )
            
            messages.success(request, f'Leave request {action.lower()} successfully')

    leave_requests = LeaveRequest.objects.all().order_by('-created_at')
    return render(request, 'attendance_core/admin/manage_leave_requests.html', {
        'leave_requests': leave_requests
    })

@login_required
@user_passes_test(is_admin)
def edit_student(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=student.user)
        profile_form = StudentProfileUpdateForm(request.POST, instance=student)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Student information updated successfully')
            return redirect('student_management')
    else:
        user_form = UserUpdateForm(instance=student.user)
        profile_form = StudentProfileUpdateForm(instance=student)
    
    return render(request, 'attendance_core/admin/edit_student.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'student': student
    })

@login_required
@user_passes_test(is_admin)
def delete_student(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    user = student.user
    user.delete()  # This will also delete the StudentProfile due to CASCADE
    messages.success(request, 'Student deleted successfully')
    return redirect('student_management')

@login_required
@user_passes_test(is_admin)
def update_news(request, news_id):
    news = get_object_or_404(News, id=news_id)
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES, instance=news)
        if form.is_valid():
            form.save()
            messages.success(request, 'News updated successfully')
            return redirect('manage_news')
    else:
        form = NewsForm(instance=news)
    
    return render(request, 'attendance_core/admin/update_news.html', {
        'form': form,
        'news': news
    })

@login_required
@user_passes_test(is_admin)
def delete_news(request, news_id):
    news = get_object_or_404(News, id=news_id)
    news.delete()
    messages.success(request, 'News deleted successfully')
    return redirect('manage_news')

@login_required
@user_passes_test(is_admin)
def admin_profile(request):
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('admin_dashboard')
    else:
        form = UserUpdateForm(instance=request.user)
    
    # Calculate statistics
    total_students = StudentProfile.objects.count()
    total_classes = StudentProfile.objects.values('class_section').distinct().count()
    
    # Calculate attendance rate for the current month
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    total_attendance = Attendance.objects.filter(date__range=[start_of_month, today]).count()
    present_attendance = Attendance.objects.filter(date__range=[start_of_month, today], status=True).count()
    attendance_rate = round((present_attendance / total_attendance * 100) if total_attendance > 0 else 0, 1)
    
    return render(request, 'attendance_core/admin/profile.html', {
        'form': form,
        'total_students': total_students,
        'total_classes': total_classes,
        'attendance_rate': attendance_rate
    })

@login_required
@user_passes_test(is_admin)
def admin_settings(request):
    if request.method == 'POST':
        if 'change_password' in request.POST:
            # Handle password change
            old_password = request.POST.get('old_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            
            if new_password1 != new_password2:
                messages.error(request, "New passwords don't match.")
            else:
                if request.user.check_password(old_password):
                    request.user.set_password(new_password1)
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Password changed successfully.")
                else:
                    messages.error(request, "Current password is incorrect.")
        
        elif 'update_notifications' in request.POST:
            # Handle notification settings
            request.user.email_notifications = request.POST.get('email_notifications') == 'on'
            request.user.sms_notifications = request.POST.get('sms_notifications') == 'on'
            request.user.leave_request_notifications = request.POST.get('leave_request_notifications') == 'on'
            request.user.news_notifications = request.POST.get('news_notifications') == 'on'
            request.user.save()
            messages.success(request, "Notification settings updated successfully.")
        
        elif 'update_privacy' in request.POST:
            # Handle privacy settings
            request.user.show_profile = request.POST.get('show_profile') == 'on'
            request.user.show_attendance = request.POST.get('show_attendance') == 'on'
            request.user.show_contact = request.POST.get('show_contact') == 'on'
            request.user.save()
            messages.success(request, "Privacy settings updated successfully.")
        
        return redirect('admin_settings')
    
    return render(request, 'attendance_core/admin/settings.html')

@login_required
@user_passes_test(is_admin)
def quick_edit_student(request):
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            student = get_object_or_404(StudentProfile, id=student_id)
            
            # Update user details
            user = student.user
            user.username = request.POST.get('username')
            user.email = request.POST.get('email')
            user.first_name = request.POST.get('first_name')
            user.last_name = request.POST.get('last_name')
            user.is_active = request.POST.get('is_active') == 'on'
            user.save()
            
            # Update student profile
            student.class_section = request.POST.get('class_section')
            student.roll_number = request.POST.get('roll_number')
            student.phone = request.POST.get('phone')
            student.address = request.POST.get('address')
            student.parent_name = request.POST.get('parent_name')
            student.parent_phone = request.POST.get('parent_phone')
            student.save()
            
            return JsonResponse({
                'success': True,
                'student_id': student.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'class_section': student.class_section,
                'roll_number': student.roll_number,
                'phone': student.phone,
                'address': student.address,
                'parent_name': student.parent_name,
                'parent_phone': student.parent_phone,
                'is_active': user.is_active
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    })

# Student Views
@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    student = request.user.student_profile
    
    # Get attendance statistics
    current_month = timezone.now().month
    current_year = timezone.now().year
    
    # Overall attendance
    total_days = Attendance.objects.filter(student=student).count()
    present_days = Attendance.objects.filter(student=student, status=True).count()
    attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
    
    # Monthly attendance
    monthly_attendance = Attendance.objects.filter(
        student=student,
        date__month=current_month,
        date__year=current_year
    )
    monthly_total = monthly_attendance.count()
    monthly_present = monthly_attendance.filter(status=True).count()
    monthly_percentage = (monthly_present / monthly_total * 100) if monthly_total > 0 else 0
    
    # Recent attendance records
    recent_attendance = Attendance.objects.filter(student=student).order_by('-date')[:10]
    
    # Get recent notifications and mark them as read
    notifications = Notification.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).order_by('-created_at')[:5]
    
    # Get recent news
    recent_news = News.objects.all().order_by('-created_at')[:3]
    
    # Get pending leave requests
    pending_leaves = LeaveRequest.objects.filter(
        student=student,
        status='PENDING'
    ).order_by('-created_at')
    
    # Calculate attendance trend
    attendance_trend = []
    for i in range(5):
        month = (timezone.now() - timedelta(days=30 * i)).month
        year = (timezone.now() - timedelta(days=30 * i)).year
        month_attendance = Attendance.objects.filter(
            student=student,
            date__month=month,
            date__year=year
        )
        month_total = month_attendance.count()
        month_present = month_attendance.filter(status=True).count()
        month_percentage = (month_present / month_total * 100) if month_total > 0 else 0
        attendance_trend.append({
            'month': timezone.now() - timedelta(days=30 * i),
            'percentage': month_percentage
        })
    
    context = {
        'student': student,
        'attendance_records': recent_attendance,
        'attendance_percentage': attendance_percentage,
        'monthly_percentage': monthly_percentage,
        'notifications': notifications,
        'recent_news': recent_news,
        'total_days': total_days,
        'present_days': present_days,
        'monthly_total': monthly_total,
        'monthly_present': monthly_present,
        'pending_leaves': pending_leaves,
        'attendance_trend': attendance_trend,
    }
    return render(request, 'attendance_core/student/dashboard.html', context)

@login_required
@user_passes_test(is_student)
def download_attendance_report(request):
    student = request.user.student_profile
    attendances = Attendance.objects.filter(student=student).order_by('-date')
    
    # Calculate statistics
    total_days = attendances.count()
    present_days = attendances.filter(status=True).count()
    attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
    
    # Generate HTML report with better styling
    html_string = f"""
    <html>
        <head>
            <title>Attendance Report for {student.student_id}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 40px;
                    color: #333;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .student-info {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 30px;
                }}
                .statistics {{
                    display: flex;
                    justify-content: space-around;
                    margin: 20px 0;
                    text-align: center;
                }}
                .stat-box {{
                    background: #fff;
                    padding: 15px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    min-width: 150px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    background: white;
                }}
                th, td {{
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                .present {{
                    color: #28a745;
                }}
                .absent {{
                    color: #dc3545;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Attendance Report</h1>
                <p>Generated on {timezone.now().strftime('%B %d, %Y')}</p>
            </div>
            
            <div class="student-info">
                <h2>{student.user.get_full_name()}</h2>
                <p><strong>Student ID:</strong> {student.student_id}</p>
                <p><strong>Class:</strong> {student.class_section}</p>
            </div>
            
            <div class="statistics">
                <div class="stat-box">
                    <h3>Total Days</h3>
                    <p>{total_days}</p>
                </div>
                <div class="stat-box">
                    <h3>Present Days</h3>
                    <p>{present_days}</p>
                </div>
                <div class="stat-box">
                    <h3>Attendance</h3>
                    <p>{attendance_percentage:.1f}%</p>
                </div>
            </div>

            <table>
                <tr>
                    <th>Date</th>
                    <th>Day</th>
                    <th>Status</th>
                </tr>
    """
    
    for attendance in attendances:
        status_class = 'present' if attendance.status else 'absent'
        status_text = 'Present' if attendance.status else 'Absent'
        html_string += f"""
                <tr>
                    <td>{attendance.date.strftime('%B %d, %Y')}</td>
                    <td>{attendance.date.strftime('%A')}</td>
                    <td class="{status_class}">{status_text}</td>
                </tr>
        """
    
    html_string += """
            </table>
        </body>
    </html>
    """
    
    return HttpResponse(html_string, content_type='text/html')

@login_required
@user_passes_test(is_student)
def student_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.student = request.user.student_profile
            leave_request.save()
            messages.success(request, 'Leave request submitted successfully')
            return redirect('student_leave_request')
    else:
        form = LeaveRequestForm()

    leave_requests = LeaveRequest.objects.filter(student=request.user.student_profile)
    return render(request, 'attendance_core/student/leave_request.html', {
        'form': form,
        'leave_requests': leave_requests
    })

@login_required
@user_passes_test(is_student)
def student_news(request):
    news_list = News.objects.all()
    return render(request, 'attendance_core/student/news.html', {
        'news_list': news_list
    })

@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'success'})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Handle AJAX request
                if user.is_staff:
                    return JsonResponse({
                        'success': True,
                        'redirect_url': reverse('admin_dashboard')
                    })
                else:
                    return JsonResponse({
                        'success': True,
                        'redirect_url': reverse('student_dashboard')
                    })
            else:
                # Handle regular form submission
                if user.is_staff:
                    return redirect('admin_dashboard')
                else:
                    return redirect('student_dashboard')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Return JSON response for AJAX request
                return JsonResponse({
                    'success': False,
                    'errors': {
                        'username': 'Invalid username or password',
                        'password': 'Invalid username or password'
                    }
                }, status=400)
            else:
                # Handle regular form submission
                messages.error(request, 'Invalid username or password')
    
    return render(request, 'attendance_core/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

@login_required
def student_profile(request):
    student = request.user.student_profile
    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('student_dashboard')
    else:
        form = StudentProfileForm(instance=student)
    
    return render(request, 'attendance_core/student/profile.html', {
        'form': form,
        'student': student
    })

@login_required
def news_detail(request, news_id):
    news = get_object_or_404(News, id=news_id)
    return render(request, 'attendance_core/student/news_detail.html', {
        'news': news
    })

@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect')
            return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')
            
        if new_password1 != new_password2:
            messages.error(request, 'New passwords do not match')
            return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')
            
        request.user.set_password(new_password1)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password changed successfully')
        return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')
    
    return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')

@login_required
def update_notification_settings(request):
    if request.method == 'POST':
        if request.user.is_staff:
            # For admin users, we'll store these in the user model or create a separate model
            pass
        else:
            student = request.user.student_profile
            student.email_notifications = request.POST.get('email_notifications') == 'on'
            student.sms_notifications = request.POST.get('sms_notifications') == 'on'
            student.leave_request_notifications = request.POST.get('leave_request_notifications') == 'on'
            student.news_notifications = request.POST.get('news_notifications') == 'on'
            student.save()
        
        messages.success(request, 'Notification settings updated successfully')
        return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')
    
    return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')

@login_required
def update_privacy_settings(request):
    if request.method == 'POST':
        if request.user.is_staff:
            # For admin users, we'll store these in the user model or create a separate model
            pass
        else:
            student = request.user.student_profile
            student.show_profile = request.POST.get('show_profile') == 'on'
            student.show_attendance = request.POST.get('show_attendance') == 'on'
            student.show_contact = request.POST.get('show_contact') == 'on'
            student.save()
        
        messages.success(request, 'Privacy settings updated successfully')
        return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')
    
    return redirect('admin_dashboard' if request.user.is_staff else 'student_dashboard')

@login_required
def student_settings(request):
    if request.method == 'POST':
        if 'change_password' in request.POST:
            # Handle password change
            old_password = request.POST.get('old_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            
            if new_password1 != new_password2:
                messages.error(request, "New passwords don't match.")
            else:
                if request.user.check_password(old_password):
                    request.user.set_password(new_password1)
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Password changed successfully.")
                else:
                    messages.error(request, "Current password is incorrect.")
        
        elif 'update_notifications' in request.POST:
            # Handle notification settings
            student = request.user.student_profile
            student.email_notifications = request.POST.get('email_notifications') == 'on'
            student.sms_notifications = request.POST.get('sms_notifications') == 'on'
            student.leave_request_notifications = request.POST.get('leave_request_notifications') == 'on'
            student.news_notifications = request.POST.get('news_notifications') == 'on'
            student.save()
            messages.success(request, "Notification settings updated successfully.")
        
        elif 'update_privacy' in request.POST:
            # Handle privacy settings
            student = request.user.student_profile
            student.show_profile = request.POST.get('show_profile') == 'on'
            student.show_attendance = request.POST.get('show_attendance') == 'on'
            student.show_contact = request.POST.get('show_contact') == 'on'
            student.save()
            messages.success(request, "Privacy settings updated successfully.")
        
        return redirect('student_settings')
    
    return render(request, 'attendance_core/student/settings.html')

def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Create reset link
            reset_link = request.build_absolute_uri(
                f'/admin-panel/reset-password/{uid}/{token}/'
            )
            
            # Send email
            subject = 'Password Reset Request'
            message = render_to_string('attendance_core/email/reset_password_email.html', {
                'user': user,
                'reset_link': reset_link,
            })
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            
            messages.success(request, 'Password reset link has been sent to your email.')
            return redirect('login')
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
    
    return render(request, 'attendance_core/forgot_password.html')

def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            
            if new_password1 != new_password2:
                messages.error(request, "Passwords don't match.")
            else:
                user.set_password(new_password1)
                user.save()
                messages.success(request, 'Your password has been reset successfully.')
                return redirect('login')
        
        return render(request, 'attendance_core/reset_password.html')
    else:
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('login')
