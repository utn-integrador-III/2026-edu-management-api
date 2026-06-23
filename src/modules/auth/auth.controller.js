const authService = require('./auth.service');

// RF-01
async function login(req, res) {
  try {
    const { id_number, password } = req.body;
    if (!id_number || !password) {
      return res.status(400).json({ message: 'id_number and password are required' });
    }
    const result = await authService.login(id_number, password);
    res.json(result);
  } catch (err) {
    res.status(401).json({ message: err.message });
  }
}

// RF-02
async function changePassword(req, res) {
  try {
    const { currentPassword, newPassword } = req.body;
    if (!newPassword || newPassword.length < 8) {
      return res.status(400).json({ message: 'New password must be at least 8 characters' });
    }
    await authService.changePassword(req.user.id, currentPassword, newPassword);
    res.json({ message: 'Password updated successfully' });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

// RF-03: request reset link
async function forgotPassword(req, res) {
  try {
    const { id_number } = req.body;
    await authService.forgotPassword(id_number);
    res.json({ message: 'If an account exists with that ID number, a recovery email will be sent' });
  } catch (err) {
    res.status(500).json({ message: 'Error processing the request' });
  }
}

// RF-03: apply new password with token
async function resetPassword(req, res) {
  try {
    const { token, newPassword } = req.body;
    if (!newPassword || newPassword.length < 8) {
      return res.status(400).json({ message: 'New password must be at least 8 characters' });
    }
    await authService.resetPassword(token, newPassword);
    res.json({ message: 'Password reset successfully' });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

// RF-04
async function logout(req, res) {
  try {
    const token = req.headers['authorization'].split(' ')[1];
    await authService.logout(req.user.id, token);
    res.json({ message: 'Session closed successfully' });
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

module.exports = { login, changePassword, forgotPassword, resetPassword, logout };
