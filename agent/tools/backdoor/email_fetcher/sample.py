< !DOCTYPE
html >
< html
lang = "en" >
< head >
< meta
charset = "UTF-8" / >
< meta
name = "viewport"
content = "width=device-width, initial-scale=1.0" / >
< title > Genesis
AI
Chatbot < / title >
< link
href = "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
rel = "stylesheet" >
< link
href = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css"
rel = "stylesheet" >

< style >
:root
{
    --primary - color:  # 667eea;
        --primary - dark:  # 5a6fd8;
--secondary - color:  # 764ba2;
--accent - color:  # f093fb;
--success - color:  # 10b981;
--error - color:  # ef4444;
--text - primary:  # 1f2937;
--text - secondary:  # 6b7280;
--bg - primary:  # ffffff;
--bg - secondary:  # f8fafc;
--border - color:  # e5e7eb;
--shadow - sm: 0
1
px
2
px
0
rgb(0
0
0 / 0.05);
--shadow - md: 0
4
px
6
px - 1
px
rgb(0
0
0 / 0.1);
--shadow - lg: 0
10
px
15
px - 3
px
rgb(0
0
0 / 0.1);
--shadow - xl: 0
20
px
25
px - 5
px
rgb(0
0
0 / 0.1);
}

*{
    box - sizing: border - box;
}

body
{
    font - family: 'Inter', sans - serif;
background: linear - gradient(135
deg,  # 667eea 0%, #764ba2 100%);
min - height: 100
vh;
margin: 0;
padding: 20
px;
display: flex;
justify - content: center;
align - items: center;
}

.chat - container
{
    width: 100 %;
max - width: 800
px;
height: 90
vh;
background: var(--bg - primary);
border - radius: 20
px;
box - shadow: var(--shadow - xl);
display: flex;
flex - direction: column;
overflow: hidden;
position: relative;
}

.chat - header
{
    background: linear - gradient(135deg, var(--primary - color), var(--secondary - color));
color: white;
padding: 20
px
25
px;
display: flex;
align - items: center;
gap: 15
px;
position: relative;
}

.chat - header::before
{
    content: '';
position: absolute;
top: 0;
left: 0;
right: 0;
bottom: 0;
background: linear - gradient(45
deg, rgba(255, 255, 255, 0.1), transparent);
pointer - events: none;
}

.ai - avatar
{
    width: 50px;
height: 50
px;
border - radius: 50 %;
background: linear - gradient(135
deg, var(--accent - color),  # f093fb);
display: flex;
align - items: center;
justify - content: center;
font - size: 24
px;
box - shadow: 0
4
px
12
px
rgba(0, 0, 0, 0.2);
animation: pulse
2
s
infinite;
}

@keyframes


pulse
{
    0 %, 100 % {transform: scale(1);}
50 % {transform: scale(1.05);}
}

.header - info
h2
{
    margin: 0;
font - size: 24
px;
font - weight: 600;
}

.header - info.status
{
    font - size: 14px;
opacity: 0.9;
display: flex;
align - items: center;
gap: 8
px;
}

.status - dot
{
    width: 8px;
height: 8
px;
border - radius: 50 %;
background:  # 10b981;
animation: blink
1.5
s
infinite;
}

@keyframes


blink
{
    0 %, 50 % {opacity: 1;}
51 %, 100 % {opacity: 0.5;}
}

.chat - actions
{
    margin - left: auto;
display: flex;
gap: 10
px;
}

.action - btn
{
    background: rgba(255, 255, 255, 0.2);
border: none;
color: white;
padding: 8
px
12
px;
border - radius: 8
px;
cursor: pointer;
transition: all
0.2
s
ease;
font - size: 14
px;
}

.action - btn: hover
{
    background: rgba(255, 255, 255, 0.3);
transform: translateY(-1
px);
}

# chat {
flex: 1;
overflow - y: auto;
padding: 20
px;
background: var(--bg - secondary);
scroll - behavior: smooth;
position: relative;
}

# chat::-webkit-scrollbar {
width: 6
px;
}

# chat::-webkit-scrollbar-track {
background: transparent;
}

# chat::-webkit-scrollbar-thumb {
background: var(--border - color);
border - radius: 3
px;
}

.message
{
    display: flex;
margin: 15
px
0;
animation: messageSlide
0.3
s
ease - out;
}

@keyframes


messageSlide
{
from

{
opacity: 0;
transform: translateY(10
px);
}
to
{
opacity: 1;
transform: translateY(0);
}
}

.message.user
{
    justify - content: flex - end;
}

.message.bot
{
    justify - content: flex - start;
}

.message - content
{
    max - width: 70 %;
padding: 15
px
20
px;
border - radius: 18
px;
font - size: 15
px;
line - height: 1.5;
white - space: pre - wrap;
position: relative;
box - shadow: var(--shadow - sm);
}

.user.message - content
{
    background: linear - gradient(135deg, var(--primary - color), var(--primary - dark));
color: white;
border - bottom - right - radius: 6
px;
}

.bot.message - content
{
    background: var(--bg - primary);
color: var(--text - primary);
border: 1
px
solid
var(--border - color);
border - bottom - left - radius: 6
px;
}

.message - time
{
    font - size: 12px;
opacity: 0.6;
margin - top: 5
px;
text - align: right;
}

.bot.message - time
{
    text - align: left;
}

.typing - indicator
{
    display: flex;
align - items: center;
gap: 10
px;
padding: 15
px
20
px;
background: var(--bg - primary);
border - radius: 18
px;
border - bottom - left - radius: 6
px;
max - width: 70 %;
border: 1
px
solid
var(--border - color);
box - shadow: var(--shadow - sm);
}

.typing - dots
{
    display: flex;
gap: 4
px;
}

.typing - dot
{
    width: 8px;
height: 8
px;
border - radius: 50 %;
background: var(--text - secondary);
animation: typing
1.4
s
infinite;
}

.typing - dot: nth - child(1)
{animation - delay: 0s;}
.typing - dot: nth - child(2)
{animation - delay: 0.2s;}
.typing - dot: nth - child(3)
{animation - delay: 0.4s;}

@keyframes


typing
{
    0 %, 60 %, 100 % {transform: scale(1);
opacity: 0.5;}
30 % {transform: scale(1.2);
opacity: 1;}
}

.input - container
{
    padding: 20px;
background: var(--bg - primary);
border - top: 1
px
solid
var(--border - color);
}

.input - group
{
    display: flex;
gap: 12
px;
align - items: flex - end;
background: var(--bg - secondary);
border - radius: 25
px;
padding: 8
px;
border: 2
px
solid
transparent;
transition: all
0.2
s
ease;
}

.input - group: focus - within
{
    border - color: var(--primary - color);
box - shadow: 0
0
0
3
px
rgba(102, 126, 234, 0.1);
}

# userInput {
flex: 1;
border: none;
background: transparent;
padding: 12
px
16
px;
font - size: 15
px;
color: var(--text - primary);
resize: none;
outline: none;
font - family: inherit;
min - height: 20
px;
max - height: 120
px;
overflow - y: auto;
}

# userInput::placeholder {
color: var(--text - secondary);
}

.send - btn
{
    background: linear - gradient(135deg, var(--primary - color), var(--primary - dark));
color: white;
border: none;
padding: 12
px
20
px;
border - radius: 20
px;
font - weight: 600;
cursor: pointer;
transition: all
0.2
s
ease;
display: flex;
align - items: center;
gap: 8
px;
font - size: 14
px;
box - shadow: var(--shadow - md);
}

.send - btn: hover:not (:disabled)
{
    transform: translateY(-1px);
box - shadow: var(--shadow - lg);
}

.send - btn: disabled
{
    opacity: 0.6;
cursor: not -allowed;
}

.error - message
{
    background:  # fee2e2;
        border: 1
px
solid  # fecaca;
color: var(--error - color);
padding: 12
px;
border - radius: 8
px;
margin: 10
px
0;
display: flex;
align - items: center;
gap: 8
px;
}

.welcome - message
{
    text - align: center;
color: var(--text - secondary);
margin: 40
px
0;
font - size: 16
px;
}

.welcome - message.emoji
{
    font - size: 48px;
margin - bottom: 16
px;
display: block;
}

.quick - actions
{
    display: flex;
gap: 10
px;
flex - wrap: wrap;
margin - top: 15
px;
}

.quick - action
{
    background: var(--bg - primary);
border: 1
px
solid
var(--border - color);
padding: 8
px
16
px;
border - radius: 20
px;
font - size: 14
px;
cursor: pointer;
transition: all
0.2
s
ease;
}

.quick - action: hover
{
    background: var(--primary - color);
color: white;
transform: translateY(-1
px);
}

@media(max - width

: 768
px) {
    body
{
    padding: 10px;
}

.chat - container
{
    height: 95vh;
border - radius: 15
px;
}

.chat - header
{
    padding: 15px 20px;
}

.header - info
h2
{
    font - size: 20px;
}

.message - content
{
    max - width: 85 %;
padding: 12
px
16
px;
}

.input - container
{
    padding: 15px;
}

.quick - actions
{
    justify - content: center;
}
}
< / style >
    < / head >
        < body >

        < div


class ="chat-container" >

< div


class ="chat-header" >

< div


class ="ai-avatar" >

< i


class ="fas fa-robot" > < / i >

< / div >
< div


class ="header-info" >

< h2 > Genesis
AI < / h2 >
< div


class ="status" >

< span


class ="status-dot" > < / span >


Up & Active
< / div >
< / div >
< div


class ="chat-actions" >

< button


class ="action-btn" onclick="clearChat()" >

< i


class ="fas fa-trash" > < / i >

< / button >
< button


class ="action-btn" onclick="exportChat()" >

< i


class ="fas fa-download" > < / i >

< / button >
< / div >
< / div >

< div
id = "chat" >
< div


class ="welcome-message" >

< span


class ="emoji" > 🤖 < / span >

< div > I
'm Genesis, your AI assistant.</div>
< br >
< div > Get
up and busy < / div >
< div


class ="quick-actions" >

< div


class ="quick-action" onclick="sendQuickMessage('What can you help me with?')" >


Send
emails?
< / div >
< div


class ="quick-action" onclick="sendQuickMessage('Tell me a joke')" >


Scrape
google
map?
< / div >
< div


class ="quick-action" onclick="sendQuickMessage('Help me brainstorm ideas')" >


Launch
Meta
Campaign
< / div >
< / div >
< / div >
< / div >

< div


class ="input-container" >

< div


class ="input-group" >

< textarea
id = "userInput"
placeholder = "owoicho, what's the move?"
rows = "1"
autofocus
> < / textarea >
< button


class ="send-btn" onclick="sendMessage()" id="sendBtn" >

< i


class ="fas fa-paper-plane" > < / i >


Send
< / button >
< / div >
< / div >
< / div >

< script >
let
messageCount = 0;
let
isTyping = false;

// Auto - resize
textarea
const
textarea = document.getElementById('userInput');
textarea.addEventListener('input', function()
{
    this.style.height = 'auto';
this.style.height = this.scrollHeight + 'px';
});

// Handle
Enter
key(Shift + Enter for new line)
textarea.addEventListener('keydown', function(e)
{
if (e.key === 'Enter' & & !e.shiftKey)
{
    e.preventDefault();
sendMessage();
}
});

function
getCurrentTime()
{
return new
Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

function
showTypingIndicator()
{
const
chat = document.getElementById('chat');
const
typingDiv = document.createElement('div');
typingDiv.className = 'message bot';
typingDiv.id = 'typing-indicator';
typingDiv.innerHTML = `
< div


class ="typing-indicator" >

< div


class ="typing-dots" >

< div


class ="typing-dot" > < / div >

< div


class ="typing-dot" > < / div >

< div


class ="typing-dot" > < / div >

< / div >
< span > Genesis is typing... < / span >
< / div >
`;
chat.appendChild(typingDiv);
chat.scrollTop = chat.scrollHeight;
}

function
hideTypingIndicator()
{
const
typingIndicator = document.getElementById('typing-indicator');
if (typingIndicator) {
typingIndicator.remove();
}
}

function
addMessage(content, isUser=false)
{
const
chat = document.getElementById('chat');
const
messageDiv = document.createElement('div');
messageDiv.className = `message ${isUser ? 'user': 'bot'}`;

const
time = getCurrentTime();
messageDiv.innerHTML = `
< div


class ="message-content" >

${content}
< div


class ="message-time" > ${time} < / div >

< / div >
`;

chat.appendChild(messageDiv);
chat.scrollTop = chat.scrollHeight;
messageCount + +;

// Remove
welcome
message
after
first
interaction
if (messageCount === 1) {
const welcomeMsg = document.querySelector('.welcome-message');
if (welcomeMsg) {
welcomeMsg.style.animation = 'messageSlide 0.3s ease-out reverse';
setTimeout(() = > welcomeMsg.remove(), 300);
}
}
}

function
showError(message)
{
const
chat = document.getElementById('chat');
const
errorDiv = document.createElement('div');
errorDiv.className = 'error-message';
errorDiv.innerHTML = `
< i


class ="fas fa-exclamation-triangle" > < / i >

< span >${message} < / span >
`;
chat.appendChild(errorDiv);
chat.scrollTop = chat.scrollHeight;
}

function
toggleSendButton(disabled)
{
const
sendBtn = document.getElementById('sendBtn');
sendBtn.disabled = disabled;
if (disabled) {
sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
} else {
sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Send';
}
}

async function
sendMessage()
{
const
input = document.getElementById('userInput');
const
message = input.value.trim();
if (!message | | isTyping) return;

isTyping = true;
toggleSendButton(true);

// Add
user
message
addMessage(message, true);
input.value = '';
input.style.height = 'auto';

// Show
typing
indicator
showTypingIndicator();

try {
const response = await fetch("http://localhost:8000/api/genesis-agent/", {
method: "POST",
headers: {"Content-Type": "application/json"},
body: JSON.stringify({user_input: message})
});

const
contentType = response.headers.get("content-type");

if (!response.ok)
{
    throw
new
Error(`Server
error: ${response.status}
`);
} else if (!contentType | | !contentType.includes("application/json")) {
const text = await response.text();
throw new Error(`Expected JSON response, got HTML.Server might be down.`);
}

const data = await response.json();
const reply = data.result ?? data.message ?? "No reply from server.";

// Simulate realistic typing delay
setTimeout(() = > {
hideTypingIndicator();
addMessage(reply);
isTyping = false;
toggleSendButton(false);
}, 1000 + Math.random() * 1000);

} catch (err) {
hideTypingIndicator();
showError(`Connection error: $
    {err.message}
`);
isTyping = false;
toggleSendButton(false);
}
}

function
sendQuickMessage(message)
{
const
input = document.getElementById('userInput');
input.value = message;
sendMessage();
}

function
clearChat()
{
const
chat = document.getElementById('chat');
chat.innerHTML = '';
messageCount = 0;

// Add
welcome
message
back
chat.innerHTML = `
< div


class ="welcome-message" >

< span


class ="emoji" > 🤖 < / span >

< div > Chat
cleared! I
'm ready for a fresh start.</div>
< div > What
would
you
like
to
talk
about? < / div >
< / div >
`;
}

function
exportChat()
{
const
messages = document.querySelectorAll('.message');
let
chatText = 'Genesis AI Chat Export\n';
chatText += '='.repeat(30) + '\n\n';

messages.forEach((msg, index) = > {
    const
isUser = msg.classList.contains('user');
const
content = msg.querySelector('.message-content').textContent.trim();
const
time = msg.querySelector('.message-time').textContent;

chatText += `${isUser ? 'You': 'Genesis'} [${time}]:\n${content}\n\n
`;
});

const
blob = new
Blob([chatText], {type: 'text/plain'});
const
url = URL.createObjectURL(blob);
const
a = document.createElement('a');
a.href = url;
a.download = `genesis - chat -${new
Date().toISOString().split('T')[0]}.txt
`;
a.click();
URL.revokeObjectURL(url);
}

// Initialize
document.addEventListener('DOMContentLoaded', function()
{
    const
input = document.getElementById('userInput');
input.focus();
});
< / script >

    < / body >
        < / html >