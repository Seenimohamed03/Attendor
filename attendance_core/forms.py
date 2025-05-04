from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import StudentProfile, Attendance, LeaveRequest, News

class StudentRegistrationForm(UserCreationForm):
    roll_number = forms.CharField(max_length=20)
    class_section = forms.CharField(max_length=10)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2', 'first_name', 'last_name', 'roll_number', 'class_section')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Create student profile with proper student_id format
            student = StudentProfile.objects.create(
                user=user,
                student_id=f'STD{user.id:03d}',
                class_section=self.cleaned_data['class_section']
            )
            # Update roll number separately
            student.roll_number = self.cleaned_data['roll_number']
            student.save()
        return user

class AttendanceUploadForm(forms.Form):
    csv_file = forms.FileField()
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

class AttendanceMarkForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['status']
        widgets = {
            'status': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['from_date', 'to_date', 'reason', 'document']
        widgets = {
            'from_date': forms.DateInput(attrs={'type': 'date'}),
            'to_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 4}),
            'document': forms.FileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'})
        }

class NewsForm(forms.ModelForm):
    class Meta:
        model = News
        fields = ['title', 'description', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4})
        }

class DateRangeForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    class_section = forms.CharField(required=False)

class StudentProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ['student_id', 'class_section', 'phone', 'address', 'emergency_contact', 'profile_picture']
        widgets = {
            'student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'class_section': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
        }

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ['student_id', 'profile_picture', 'phone', 'address', 'parent_phone']
        widgets = {
            'student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }