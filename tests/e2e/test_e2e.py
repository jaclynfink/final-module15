from uuid import uuid4
import re

import pytest
from playwright.sync_api import expect


def _register_and_open_home(page) -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    username = f'e2e_calc_{suffix}'
    email = f'{username}@example.com'

    page.goto('http://127.0.0.1:8000/register')
    page.fill('#username', username)
    page.fill('#email', email)
    page.fill('#password', 'ValidPassword123')
    page.click('#register-form button[type="submit"]')
    expect(page.locator('#status')).to_contain_text('Registration successful')

    page.goto('http://127.0.0.1:8000/')
    expect(page.locator('#auth-status')).to_contain_text(f'Logged in as {username}.')
    return username, email


@pytest.mark.e2e
def test_register_page_creates_user_and_stores_token(page, fastapi_server):
    suffix = uuid4().hex[:8]
    username = f'playwright_{suffix}'
    email = f'{username}@example.com'

    page.goto('http://127.0.0.1:8000/register')

    page.fill('#username', username)
    page.fill('#email', email)
    page.fill('#password', 'ValidPassword123')
    page.click('#register-form button[type="submit"]')

    expect(page.locator('#status')).to_contain_text(f'Registration successful for {username}.')
    token = page.evaluate("() => localStorage.getItem('access_token')")
    assert token is not None
    assert len(token.split('.')) == 3


@pytest.mark.e2e
def test_register_page_rejects_short_password_with_frontend_validation(page, fastapi_server):
    suffix = uuid4().hex[:8]
    username = f'pw_short_{suffix}'
    email = f'{username}@example.com'

    page.goto('http://127.0.0.1:8000/register')
    page.fill('#username', username)
    page.fill('#email', email)
    page.fill('#password', 'hi')
    page.click('#register-form button[type="submit"]')

    is_invalid = page.evaluate("""
        () => {
            const password = document.getElementById('password');
            return !password.checkValidity() && password.validationMessage.length > 0;
        }
    """)
    assert is_invalid is True

    token = page.evaluate("() => localStorage.getItem('access_token')")
    assert token is None


@pytest.mark.e2e
def test_login_page_accepts_email_identifier(page, fastapi_server):
    suffix = uuid4().hex[:8]
    username = f'login_playwright_{suffix}'
    email = f'{username}@example.com'

    page.goto('http://127.0.0.1:8000/register')
    page.fill('#username', username)
    page.fill('#email', email)
    page.fill('#password', 'ValidPassword123')
    page.click('#register-form button[type="submit"]')
    expect(page.locator('#status')).to_contain_text('Registration successful')

    page.goto('http://127.0.0.1:8000/login')
    page.fill('#identifier', email)
    page.fill('#password', 'ValidPassword123')
    page.click('#login-form button[type="submit"]')

    expect(page).to_have_url('http://127.0.0.1:8000/?logged_in=1')
    expect(page.locator('#auth-status')).to_have_text(f'Logged in as {username}.')
    user = page.evaluate("() => JSON.parse(localStorage.getItem('current_user'))")
    assert user['username'] == username


@pytest.mark.e2e
def test_login_page_shows_invalid_credentials(page, fastapi_server):
    page.goto('http://127.0.0.1:8000/login')

    page.fill('#identifier', 'missing_user')
    page.fill('#password', 'WrongPassword123')
    with page.expect_response(
        lambda response: response.url.endswith('/login') and response.status == 401
    ) as login_response:
        page.click('#login-form button[type="submit"]')

    assert login_response.value.status == 401

    expect(page.locator('#status')).to_have_text('Invalid username or password.')


@pytest.mark.e2e
def test_calculation_bread_positive_create_read_update_delete(page, fastapi_server):
    _register_and_open_home(page)

    # Add
    page.fill('#add-a', '10')
    page.fill('#add-b', '5')
    page.select_option('#add-type', 'Add')
    page.click('#add-form button[type="submit"]')
    expect(page.locator('#bread-feedback')).to_contain_text('Created calculation #')
    expect(page.locator('#history-status')).to_contain_text('Loaded')
    expect(page.locator('#history-list li')).to_have_count(1)
    expect(page.locator('#history-list li').first).to_contain_text('10')

    item_text = page.locator('#history-list li').first.inner_text()
    match = re.search(r'#(\d+)', item_text)
    assert match is not None
    calculation_id = int(match.group(1))

    # Read
    page.fill('#read-id', str(calculation_id))
    page.click('#read-form button[type="submit"]')
    expect(page.locator('#bread-feedback')).to_contain_text(f'Read #{calculation_id}:')

    # Update
    page.fill('#edit-id', str(calculation_id))
    page.fill('#edit-a', '9')
    page.fill('#edit-b', '3')
    page.select_option('#edit-type', 'Multiply')
    page.click('#edit-form button[type="submit"]')
    expect(page.locator('#bread-feedback')).to_contain_text(f'Updated calculation #{calculation_id}.')
    expect(page.locator('#history-list li').first).to_contain_text('9')
    expect(page.locator('#history-list li').first).to_contain_text('Multiply')

    # Delete
    page.fill('#delete-id', str(calculation_id))
    page.click('#delete-form button[type="submit"]')
    expect(page.locator('#bread-feedback')).to_contain_text(f'Deleted calculation #{calculation_id}.')
    expect(page.locator('#history-list li')).to_have_count(0)


@pytest.mark.e2e
def test_calculation_bread_negative_invalid_input_divide_by_zero(page, fastapi_server):
    _register_and_open_home(page)

    page.fill('#add-a', '10')
    page.fill('#add-b', '0')
    page.select_option('#add-type', 'Divide')
    page.click('#add-form button[type="submit"]')

    expect(page.locator('#bread-feedback')).to_have_text('Cannot divide by zero.')
    expect(page.locator('#bread-feedback')).to_have_class(re.compile(r'.*error.*'))


@pytest.mark.e2e
def test_calculation_bread_negative_unauthorized_access_shows_feedback(page, fastapi_server):
    page.goto('http://127.0.0.1:8000/')
    page.evaluate("""
        () => {
            localStorage.removeItem('current_user');
            localStorage.removeItem('access_token');
        }
    """)
    page.reload()

    page.fill('#read-id', '1')
    page.click('#read-form button[type="submit"]')

    expect(page.locator('#bread-feedback')).to_have_text('Please log in first.')
    expect(page.locator('#bread-feedback')).to_have_class(re.compile(r'.*error.*'))


@pytest.mark.e2e
def test_calculation_bread_negative_not_found_error_response(page, fastapi_server):
    _register_and_open_home(page)

    page.fill('#read-id', '999999')
    page.click('#read-form button[type="submit"]')

    expect(page.locator('#bread-feedback')).to_contain_text('Calculation not found.')
    expect(page.locator('#bread-feedback')).to_have_class(re.compile(r'.*error.*'))
