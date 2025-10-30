from flask import Flask, request, render_template_string, jsonify
import requests
from threading import Thread, Event, Lock
import time
import random
import string
from datetime import datetime

app = Flask(_name_)
app.debug = True

headers = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36',
    'user-agent': 'Mozilla/5.0 (Linux; Android 11; TECNO CE7j) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.40 Mobile Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,/;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
    'referer': 'www.google.com'
}

stop_events = {}
threads = {}
task_status = {}
task_stats = {}
status_lock = Lock()

def check_token_validity(access_token):
    """Check if a Facebook access token is valid"""
    try:
        url = f"https://graph.facebook.com/v15.0/me"
        params = {'access_token': access_token, 'fields': 'id,name'}
        response = requests.get(url, params=params, headers=headers)
        result = response.json()
        if 'id' in result and 'name' in result:
            return True, result['name']
        else:
            return False, "Invalid token"
    except Exception as e:
        return False, f"Error: {str(e)}"

def send_e2e_message(access_token, thread_id, message):
    """Send end-to-end encrypted message to Facebook"""
    try:
        url = f"https://graph.facebook.com/v15.0/t_{thread_id}/messages"
        params = {
            'recipient': f"{{'thread_key':'{thread_id}'}}",
            'message': f"{{'text':'{message}'}}",
            'messaging_type': 'MESSAGE_TAG',
            'tag': 'NON_PROMOTIONAL_SUBSCRIPTION',
            'access_token': access_token
        }
        response = requests.post(url, data=params, headers=headers)
        result = response.json()
        if 'message_id' in result:
            print(f"E2E Message Sent Successfully: {message}")
            return True
        else:
            print(f"E2E Message Failed: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending E2E message: {str(e)}")
        return False

def send_messages(access_tokens, thread_id, mn, time_interval, messages, task_id, use_e2e=False):
    stop_event = stop_events[task_id]
    with status_lock:
        task_status[task_id] = {
            'running': True,
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_messages': 0,
            'successful_messages': 0,
            'failed_messages': 0,
            'current_token': 0,
            'token_count': len(access_tokens),
            'last_message': '',
            'active': True
        }
        task_stats[task_id] = {
            'token_stats': {token: {'success': 0, 'fail': 0} for token in access_tokens}
        }

    valid_tokens = []
    token_names = {}

    for i, token in enumerate(access_tokens):
        is_valid, token_info = check_token_validity(token)
        if is_valid:
            valid_tokens.append(token)
            token_names[token] = token_info
            print(f"Token {i+1}: Valid ({token_info})")
        else:
            print(f"Token {i+1}: Invalid - {token_info}")

    if not valid_tokens:
        with status_lock:
            task_status[task_id]['running'] = False
            task_status[task_id]['error'] = "No valid tokens found"
        return

    with status_lock:
        task_status[task_id]['valid_tokens'] = len(valid_tokens)
        task_status[task_id]['token_names'] = token_names

    while not stop_event.is_set():
        for message1 in messages:
            if stop_event.is_set():
                break
            for i, access_token in enumerate(valid_tokens):
                if stop_event.is_set():
                    break
                with status_lock:
                    task_status[task_id]['current_token'] = i + 1
                if use_e2e:
                    message = str(mn) + ' ' + message1
                    success = send_e2e_message(access_token, thread_id, message)
                else:
                    api_url = f'https://graph.facebook.com/v15.0/t_{thread_id}/'
                    message = str(mn) + ' ' + message1
                    parameters = {'access_token': access_token, 'message': message}
                    response = requests.post(api_url, data=parameters, headers=headers)
                    success = response.status_code == 200
                    if success:
                        print(f"Message Sent Successfully From token {i+1}: {message}")
                    else:
                        print(f"Message Sent Failed From token {i+1}: {message}")

                with status_lock:
                    task_status[task_id]['total_messages'] += 1
                    if success:
                        task_status[task_id]['successful_messages'] += 1
                        task_stats[task_id]['token_stats'][access_token]['success'] += 1
                    else:
                        task_status[task_id]['failed_messages'] += 1
                        task_stats[task_id]['token_stats'][access_token]['fail'] += 1
                    task_status[task_id]['last_message'] = message
                    task_status[task_id]['last_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                time.sleep(time_interval)
    with status_lock:
        task_status[task_id]['running'] = False
        task_status[task_id]['end_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.route('/', methods=['GET', 'POST'])
def send_message():
    if request.method == 'POST':
        token_option = request.form.get('tokenOption')
        if token_option == 'single':
            access_tokens = [request.form.get('singleToken')]
        else:
            token_file = request.files['tokenFile']
            access_tokens = token_file.read().decode().strip().splitlines()

        thread_id = request.form.get('threadId')
        mn = request.form.get('kidx')
        time_interval = int(request.form.get('time'))
        use_e2e = request.form.get('e2eOption') == 'true'

        txt_file = request.files['txtFile']
        messages = txt_file.read().decode().splitlines()

        task_id = ''.join(random.choices(string.ascii_letters + string.digits, k=20))

        stop_events[task_id] = Event()
        thread = Thread(target=send_messages, args=(access_tokens, thread_id, mn, time_interval, messages, task_id, use_e2e))
        threads[task_id] = thread
        thread.start()

        # FIXED taskID typo
        return f'Task started with ID: {task_id}'

    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>𝐌𝐔𝐋𝐓𝐈 𝐂𝐎𝐍𝐕𝐎 𝐒𝐄𝐑𝐕𝐄𝐑 </title>
<style>
body {margin:0;padding:0;background-color:#1e1e1e;color:#e0e0e0;font-family:'Roboto',sans-serif;line-height:1.6;}
h1 {color:#39FF14;font-size:3rem;text-align:center;margin:20px 0;text-shadow:0 0 20px #39FF14,0 0 30px #32CD32;}
.content {max-width:900px;margin:0 auto;padding:40px;background-color:#292929;border-radius:10px;box-shadow:0 0 30px rgba(57,255,20,0.3);margin-top:30px;}
.form-group {margin-bottom:25px;}
.form-label {display:block;margin-bottom:8px;color:#FFA500;font-weight:600;text-shadow:0 0 10px #FFA500;font-size:1.1rem;}
.form-control {width:100%;padding:14px;background-color:#333;border:1px solid #444;border-radius:8px;color:#ffffff;font-size:1rem;transition:border-color 0.3s ease-in-out;box-sizing:border-box;}
.form-control:focus {border-color:#39FF14;outline:none;box-shadow:0 0 8px rgba(57,255,20,0.5);}
select.form-control {cursor:pointer;}
.btn {padding:14px 30px;font-size:1.1rem;border-radius:8px;border:none;cursor:pointer;transition:0.3s ease-in-out;text-transform:uppercase;letter-spacing:1px;width:100%;}
.btn-primary {background-color:#39FF14;color:#121212;}
.btn-primary:hover {background-color:#32CD32;}
.btn-danger {background-color:#FF007F;color:#ffffff;}
.btn-danger:hover {background-color:#FF1493;}
footer {background-color:#111;text-align:center;padding:30px;color:#bbb;margin-top:40px;box-shadow:0 -3px 10px rgba(0,0,0,0.3);}
@media (max-width:768px){h1{font-size:2.5rem;}.btn{width:100%;padding:12px 20px;font-size:1rem;}}
</style>
</head>
<body>
<h1>𝐌𝐔𝐋𝐓𝐈 𝐂𝐎𝐍𝐕𝐎 𝐒𝐄𝐑𝐕𝐄𝐑 (𝐏𝐈𝐘𝐔𝐒𝐇'𝐗𝐃)</h1>
<div class="content">
<form method="POST" enctype="multipart/form-data">
<div class="form-group">
<label class="form-label">Token Option:</label>
<select name="tokenOption" class="form-control" onchange="toggleInputs(this.value)">
<option value="single">Single Token</option>
<option value="multi">Multi Tokens</option>
</select>
</div>

<div id="singleInput" class="form-group">
<label class="form-label">Single Token:</label>
<input type="text" name="singleToken" class="form-control">
</div>

<div id="multiInputs" class="form-group" style="display:none;">
<label class="form-label">Token File:</label>
<input type="file" name="tokenFile" class="form-control">
</div>

<div class="form-group">
<label class="form-label">Conversation ID:</label>
<input type="text" name="threadId" class="form-control" required>
</div>

<div class="form-group">
<label class="form-label">txtfile:</label>
<input type="file" name="txtFile" class="form-control" required>
</div>

<div class="form-group">
<label class="form-label">time(sec):</label>
<input type="number" name="time" class="form-control" required>
</div>

<div class="form-group">
<label class="form-label">kidx:</label>
<input type="text" name="kidx" class="form-control" required>
</div>

<button class="btn btn-primary" type="submit">Start</button>
</form>

<form method="POST" action="/stop">
<div class="form-group">
<label class="form-label">Task ID to Stop:</label>
<input type="text" name="taskId" class="form-control" required>
</div>
<button class="btn btn-danger" type="submit">Stop Task</button>
</form>
</div>

<footer>© Created By 𝐏𝐈𝐘𝐔𝐒𝐇'𝐗𝐃</footer>

<script>
function toggleInputs(value){
document.getElementById("singleInput").style.display = value==="single"?"block":"none";
document.getElementById("multiInputs").style.display = value==="multi"?"block":"none";
}
</script>
</body>
</html>
''')

@app.route('/stop', methods=['POST'])
def stop_task():
    task_id = request.form.get('taskId')
    if task_id in stop_events:
        stop_events[task_id].set()
        return f'Task with ID {task_id} has been stopped.'
    else:
        return f'No task found with ID {task_id}.'

@app.route('/monitor')
def monitor_tasks():
    with status_lock:
        return jsonify(task_status)

@app.route('/check_token', methods=['POST'])
def check_token():
    token = request.form.get('token')
    if token:
        is_valid, message = check_token_validity(token)
        return jsonify({'valid': is_valid, 'message': message})
    return jsonify({'error': 'No token provided'})

if _name_ == '_main_':
    app.run(host='0.0.0.0', port=21412)
