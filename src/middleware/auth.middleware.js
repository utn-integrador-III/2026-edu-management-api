const jwt = require('jsonwebtoken');
const db  = require('../config/database');

async function verifyToken(req, res, next) {
  const header = req.headers['authorization'];
  if (!header) return res.status(401).json({ message: 'Token required' });

  const token = header.split(' ')[1];
  if (!token) return res.status(401).json({ message: 'Invalid format' });

  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
  } catch {
    return res.status(401).json({ message: 'Invalid or expired token' });
  }

  // RF-04: verify token was not invalidated by logout
  const { rows } = await db.query(
    'SELECT id FROM token_blacklist WHERE token = $1',
    [token]
  );
  if (rows.length > 0) {
    return res.status(401).json({ message: 'Session expired. Please log in again' });
  }

  next();
}

module.exports = { verifyToken };
