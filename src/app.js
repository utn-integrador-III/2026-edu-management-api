const express   = require('express');
const cors      = require('cors');
const helmet    = require('helmet');
const morgan    = require('morgan');

const authRoutes  = require('./modules/auth/auth.routes');
const usersRoutes = require('./modules/users/users.routes');

const app = express();

app.use(helmet());
app.use(cors());
app.use(morgan('dev'));
app.use(express.json());

// Cristian — auth + users (RF-01 a RF-06)
app.use('/api/v1/auth',  authRoutes);
app.use('/api/v1/users', usersRoutes);

// TODO: agregar aquí las rutas de los demás módulos
// app.use('/api/v1/attendance',    attendanceRoutes);
// app.use('/api/v1/grades',        gradesRoutes);
// app.use('/api/v1/calendar',      calendarRoutes);
// app.use('/api/v1/notifications', notificationsRoutes);

app.get('/health', (_req, res) => res.json({ status: 'ok' }));

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ message: 'Internal server error' });
});

module.exports = app;
