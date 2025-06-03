// Функция для показа выбранной секции
function showSection(sectionId) {
    document.querySelectorAll('.section').forEach(section => {
      section.classList.remove('active');
    });
    const target = document.getElementById(sectionId);
    if (target) target.classList.add('active');
  }
  
  // Обработчики кнопок
  document.getElementById('play-btn').addEventListener('click', () => {
    showSection('play-section');
  });
  document.getElementById('settings-btn').addEventListener('click', () => {
    showSection('settings-section');
  });
  document.getElementById('logout-btn').addEventListener('click', () => {
    window.location.href = 'log_page.html';
  });
  
  // Обновление баланса с сервера
  async function updateBalance() {
    try {
      const response = await fetch('http://localhost:3000/check-balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: 1 }) // Заменить на реальный ID пользователя
      });
      if (response.ok) {
        const data = await response.json();
        document.getElementById('user-balance').textContent = data.cash;
      } else {
        console.error('Ошибка загрузки баланса');
      }
    } catch (error) {
      console.error('Ошибка при подключении к серверу:', error);
    }
  }

  // Подключение к WebSocket
const gameSocket = new WebSocket(
  'ws://' + window.location.host + '/ws/game/'
);

gameSocket.onmessage = function(e) {
  const data = JSON.parse(e.data);
  switch(data.type) {
      case 'game_update':
          updateGameState(data.game);
          break;
      case 'chat_message':
          addChatMessage(data.message);
          break;
      case 'player_joined':
          notifyPlayerJoined(data.player);
          break;
  }
};

function joinLobby(lobbyId) {
  gameSocket.send(JSON.stringify({
      'type': 'join_lobby',
      'lobby_id': lobbyId
  }));
}

function createLobby() {
  gameSocket.send(JSON.stringify({
      'type': 'create_lobby'
  }));
}

function updateGameState(gameData) {
  // Обновление интерфейса игры на основе полученных данных
  console.log('Game state updated:', gameData);
}
  
  // Тема: дневная/ночная
  document.getElementById('theme-switch').addEventListener('change', (e) => {
    document.body.classList.toggle('dark', e.target.checked);
  });
  
  // Загрузка баланса при загрузке страницы
  updateBalance();
  