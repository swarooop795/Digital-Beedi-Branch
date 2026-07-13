// Password Strength Checker
function checkPasswordStrength(password) {
    let strength = 0;
    
    // Length check
    if (password.length >= 8) strength += 1;
    
    // Contains number
    if (/\d/.test(password)) strength += 1;
    
    // Contains letter
    if (/[a-zA-Z]/.test(password)) strength += 1;
    
    // Contains special character
    if (/[!@#$%^&*]/.test(password)) strength += 1;
    
    return strength;
}

// Update password strength indicator
function updatePasswordStrength(password) {
    const strength = checkPasswordStrength(password);
    const indicator = document.querySelector('.password-strength');
    
    indicator.classList.remove('strength-weak', 'strength-medium', 'strength-strong');
    
    if (strength <= 1) {
        indicator.classList.add('strength-weak');
    } else if (strength <= 2) {
        indicator.classList.add('strength-medium');
    } else {
        indicator.classList.add('strength-strong');
    }
}

// Form submission handling
function handleSubmit(event) {
    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    
    // Show loading state
    submitBtn.classList.add('btn-loading');
    submitBtn.disabled = true;
    
    // Clear previous errors
    document.querySelectorAll('.alert').forEach(alert => alert.remove());
}

// Initialize login page
document.addEventListener('DOMContentLoaded', function() {
    // Password strength checking
    const passwordInput = document.querySelector('input[type="password"]');
    if (passwordInput) {
        passwordInput.addEventListener('input', (e) => {
            updatePasswordStrength(e.target.value);
        });
    }
    
    // Form submission
    const loginForm = document.querySelector('form');
    if (loginForm) {
        loginForm.addEventListener('submit', handleSubmit);
    }
    
    // Show password toggle
    const togglePassword = document.querySelector('.toggle-password');
    if (togglePassword) {
        togglePassword.addEventListener('click', function() {
            const password = document.querySelector('#password');
            const type = password.getAttribute('type');
            password.setAttribute('type', type === 'password' ? 'text' : 'password');
            this.querySelector('i').classList.toggle('fa-eye');
            this.querySelector('i').classList.toggle('fa-eye-slash');
        });
    }
    
    // Auto-hide alerts after 5 seconds
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});