let editIndex = null;

function loadDevices() {
  axios.get('/api/devices').then(res => {
    const tbody = document.querySelector('#deviceTable tbody');
    tbody.innerHTML = '';
    console.log("devices data:", res.data);
    res.data.forEach((d, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${d.name}</td>
        <td>${d.mac}</td>
        <td>${d.ip}</td>
        <td>${d.port || 9}</td>
        <td>
          <button class='btn btn-sm btn-success' onclick='wake(${i})'>唤醒</button>
          <button class='btn btn-sm btn-warning' onclick='edit(${i})'>编辑</button>
          <button class='btn btn-sm btn-danger' onclick='del(${i})'>删除</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  });
}

function saveDevice() {
  const data = {
    name: document.getElementById('name').value,
    mac: document.getElementById('mac').value,
    ip: document.getElementById('ip').value,
    port: document.getElementById('port').value
  };

  if (editIndex !== null) {
    axios.put(`/api/devices/${editIndex}`, data).then(loadDevices);
    editIndex = null;
  } else {
    axios.post('/api/devices', data).then(loadDevices);
  }
  clearForm();
}

function clearForm() {
  document.getElementById('name').value = '';
  document.getElementById('mac').value = '';
  document.getElementById('ip').value = '';
  document.getElementById('port').value = '9';
  editIndex = null;
}

function edit(i) {
  axios.get('/api/devices').then(res => {
    const d = res.data[i];
    document.getElementById('name').value = d.name;
    document.getElementById('mac').value = d.mac;
    document.getElementById('ip').value = d.ip;
    document.getElementById('port').value = d.port;
    editIndex = i;
  });
}

function del(i) {
  if (confirm('确定要删除该设备吗？此操作不可恢复。')) {
    axios.delete(`/api/devices/${i}`).then(loadDevices);
  }
}

function wake(i) {
  axios.post(`/api/wake/${i}`).then(() => alert('已发送唤醒包')).catch(err => alert('发送失败: ' + err));
}

window.onload = loadDevices;
