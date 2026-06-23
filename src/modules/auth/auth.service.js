const bcrypt  = require('bcryptjs');
const jwt     = require('jsonwebtoken');
const crypto  = require('crypto');
const db      = require('../../config/database');
const { transporter } = require('../../config/mailer');

// RF-01
async function login(id_number, password) {
  const { rows } = await db.query(
    'SELECT * FROM users WHERE id_number = $1 AND active = true',
    [id_number]
  );
  const user = rows[0];
  if (!user) throw new Error('Invalid credentials');

  if (user.role === 'student') throw new Error('Invalid credentials');

  const valid = await bcrypt.compare(password, user.password_hash);
  if (!valid) throw new Error('Invalid credentials');

  const token = jwt.sign(
    {
      id:                 user.id,
      role:               user.role,
      first_name:         user.first_name,
      mustChangePassword: user.must_change_password,
    },
    process.env.JWT_SECRET,
    { expiresIn: process.env.JWT_EXPIRES_IN }
  );

  return {
    token,
    mustChangePassword: user.must_change_password,
    role:               user.role,
    first_name:         user.first_name,
    last_name:          user.last_name,
  };
}

// RF-02
async function changePassword(userId, currentPassword, newPassword) {
  const { rows } = await db.query('SELECT * FROM users WHERE id = $1', [userId]);
  const user = rows[0];
  if (!user) throw new Error('User not found');

  const valid = await bcrypt.compare(currentPassword, user.password_hash);
  if (!valid) throw new Error('Current password is incorrect');

  const hash = await bcrypt.hash(newPassword, 10);
  await db.query(
    'UPDATE users SET password_hash = $1, must_change_password = false WHERE id = $2',
    [hash, userId]
  );
}

// RF-03: send reset link
async function forgotPassword(id_number) {
  const { rows } = await db.query(
    'SELECT id, email, first_name, last_name FROM users WHERE id_number = $1 AND active = true',
    [id_number]
  );
  const user = rows[0];
  if (!user || !user.email) return;

  await db.query(
    'UPDATE password_reset_tokens SET used = true WHERE user_id = $1 AND used = false',
    [user.id]
  );

  const token     = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000); // 1 hour

  await db.query(
    'INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES ($1, $2, $3)',
    [user.id, token, expiresAt]
  );

  const resetUrl = `${process.env.FRONTEND_URL || 'http://localhost:5173'}/reset-password?token=${token}`;

  await transporter.sendMail({
    from:    process.env.EMAIL_FROM,
    to:      user.email,
    subject: 'EduConecta CR — Password recovery',
    html: `
      <p>Dear ${user.first_name} ${user.last_name},</p>
      <p>We received a request to reset your EduConecta CR password.</p>
      <p>Click the link below to continue (valid for 1 hour):</p>
      <p><a href="${resetUrl}">${resetUrl}</a></p>
      <p>If you did not make this request, please ignore this email.</p>
    `,
  });
}

// RF-03: apply new password
async function resetPassword(token, newPassword) {
  const { rows } = await db.query(
    `SELECT id, user_id FROM password_reset_tokens
     WHERE token = $1 AND used = false AND expires_at > NOW()`,
    [token]
  );
  const record = rows[0];
  if (!record) throw new Error('Invalid or expired token');

  const hash = await bcrypt.hash(newPassword, 10);
  await db.query(
    'UPDATE users SET password_hash = $1, must_change_password = false WHERE id = $2',
    [hash, record.user_id]
  );
  await db.query(
    'UPDATE password_reset_tokens SET used = true WHERE id = $1',
    [record.id]
  );
}

// RF-04
async function logout(userId, token) {
  await db.query(
    'INSERT INTO token_blacklist (token, user_id) VALUES ($1, $2) ON CONFLICT (token) DO NOTHING',
    [token, userId]
  );
}

module.exports = { login, changePassword, forgotPassword, resetPassword, logout };
