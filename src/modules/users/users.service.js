const bcrypt = require('bcryptjs');
const fs     = require('fs');
const { parse } = require('csv-parse/sync');
const db     = require('../../config/database');
const { transporter } = require('../../config/mailer');

// RF-05: List users
async function getAll(filters = {}) {
  let query = `SELECT id, id_number, first_name, last_name, email, phone,
                      role, type, group_id, is_adult, active
               FROM users`;
  const params = [];
  const conditions = [];

  if (filters.role) {
    params.push(filters.role);
    conditions.push(`role = $${params.length}`);
  }
  if (filters.active !== undefined) {
    params.push(filters.active);
    conditions.push(`active = $${params.length}`);
  }

  if (conditions.length) query += ' WHERE ' + conditions.join(' AND ');
  query += ' ORDER BY last_name, first_name';

  const { rows } = await db.query(query, params);
  return rows;
}

// RF-05: Get user by ID
async function getById(id) {
  const { rows } = await db.query(
    `SELECT id, id_number, first_name, last_name, email, phone,
            role, type, group_id, is_adult, active
     FROM users WHERE id = $1`,
    [id]
  );
  return rows[0];
}

// RF-05: Create user — temp password = id_number
async function create(data) {
  const { id_number, first_name, last_name, email, phone, role, type, group_id, birth_date } = data;
  const hash = await bcrypt.hash(id_number, 10);

  const { rows } = await db.query(
    `INSERT INTO users (id_number, first_name, last_name, email, phone, role, type, group_id, birth_date, password_hash, must_change_password)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true)
     RETURNING id, id_number, first_name, last_name, email, role`,
    [id_number, first_name, last_name, email || null, phone || null, role, type || null, group_id || null, birth_date || null, hash]
  );

  if (email) {
    await _sendWelcomeEmail(email, first_name, last_name, id_number).catch(() => {});
  }

  return rows[0];
}

async function _sendWelcomeEmail(email, firstName, lastName, idNumber) {
  await transporter.sendMail({
    from:    process.env.EMAIL_FROM,
    to:      email,
    subject: 'EduConecta CR — Your access credentials',
    html: `
      <p>Dear ${firstName} ${lastName},</p>
      <p>Your EduConecta CR account has been created. Your login credentials are:</p>
      <ul>
        <li><strong>ID Number:</strong> ${idNumber}</li>
        <li><strong>Temporary password:</strong> ${idNumber}</li>
      </ul>
      <p>You will be asked to change your password on your first login.</p>
      <p>For security reasons, do not share these credentials with anyone.</p>
    `,
  });
}

// RF-05: Update user
async function update(id, data) {
  const { first_name, last_name, email, phone, role, type, group_id, active } = data;
  const { rows } = await db.query(
    `UPDATE users
     SET first_name = $1, last_name = $2, email = $3, phone = $4,
         role = $5, type = $6, group_id = $7, active = $8
     WHERE id = $9
     RETURNING id, id_number, first_name, last_name, email, role, active`,
    [first_name, last_name, email || null, phone || null, role, type || null, group_id || null, active, id]
  );
  if (!rows[0]) throw new Error('User not found');
  return rows[0];
}

// RF-05: Deactivate user
async function deactivate(id) {
  const { rowCount } = await db.query(
    'UPDATE users SET active = false WHERE id = $1',
    [id]
  );
  if (rowCount === 0) throw new Error('User not found');
}

// Subjects
async function getSubjects() {
  const { rows } = await db.query('SELECT id, name, code, level FROM subjects ORDER BY name');
  return rows;
}

async function createSubject(data) {
  const { name, code, level } = data;
  const { rows } = await db.query(
    'INSERT INTO subjects (name, code, level) VALUES ($1, $2, $3) RETURNING *',
    [name, code, level || null]
  );
  return rows[0];
}

// Groups
async function getGroups() {
  const { rows } = await db.query('SELECT id, name, level FROM groups ORDER BY name');
  return rows;
}

// Children of parent
async function getChildren(parentId) {
  const { rows } = await db.query(
    `SELECT u.id, u.first_name, u.last_name, g.name AS group_name
     FROM parent_students ps
     JOIN users u ON u.id = ps.student_id AND u.active = true
     LEFT JOIN groups g ON g.id = u.group_id
     WHERE ps.parent_id = $1
     ORDER BY u.last_name, u.first_name`,
    [parentId]
  );
  return rows;
}

// RF-06: Get student subjects
async function getStudentSubjects(studentId, period) {
  const { rows } = await db.query(
    `SELECT s.id, s.name, s.code, s.level,
            u.first_name || ' ' || u.last_name AS teacher_name,
            g.name AS group_name, ss.period
     FROM student_subjects ss
     JOIN subjects s ON s.id = ss.subject_id
     LEFT JOIN users  u ON u.id = ss.teacher_id
     LEFT JOIN groups g ON g.id = ss.group_id
     WHERE ss.student_id = $1
       AND ($2::VARCHAR IS NULL OR ss.period = $2)
     ORDER BY s.name`,
    [studentId, period || null]
  );
  return rows;
}

// RF-06: Assign subjects to student
async function assignSubjectsToStudent(studentId, assignments) {
  const { rows: userRows } = await db.query(
    'SELECT id FROM users WHERE id = $1 AND role = $2 AND active = true',
    [studentId, 'student']
  );
  if (!userRows[0]) throw new Error('Student not found or inactive');

  const client = await db.connect();
  try {
    await client.query('BEGIN');
    for (const { subject_id, teacher_id, group_id, period } of assignments) {
      await client.query(
        `INSERT INTO student_subjects (student_id, subject_id, teacher_id, group_id, period)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (student_id, subject_id, period)
         DO UPDATE SET teacher_id = EXCLUDED.teacher_id, group_id = EXCLUDED.group_id`,
        [studentId, subject_id, teacher_id || null, group_id || null, period || '2026']
      );
    }
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

// RF-06: Remove subject from student
async function removeStudentSubject(studentId, subjectId, period) {
  await db.query(
    'DELETE FROM student_subjects WHERE student_id = $1 AND subject_id = $2 AND period = $3',
    [studentId, subjectId, period || '2026']
  );
}

// CSV import: Users — formato Caleb: cedula;nombre;apellido1;apellido2;correo;telefono;tipo_usuario;accion
async function importUsersFromCSV(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const records = parse(content, { columns: true, skip_empty_lines: true, trim: true, delimiter: ';' });

  const results = { created: 0, updated: 0, deactivated: 0, skipped: 0, errors: [] };

  for (const row of records) {
    const accion = (row.accion || '').trim().toLowerCase();
    const tipo   = (row.tipo_usuario || '').trim().toLowerCase();
    const role   = tipo.startsWith('doc') ? 'teacher' : 'parent';

    try {
      if (['insertar', 'insert', 'crear'].includes(accion)) {
        await create({
          id_number:  row.cedula,
          first_name: row.nombre,
          last_name:  `${row.apellido1} ${row.apellido2}`.trim(),
          email:      row.correo   || null,
          phone:      row.telefono || null,
          role,
        });
        results.created++;
      } else if (['update', 'actualizar', 'modificar'].includes(accion)) {
        const { rows: found } = await db.query('SELECT id FROM users WHERE id_number = $1', [row.cedula]);
        if (!found[0]) { results.errors.push({ row: row.cedula, error: 'Not found for update' }); continue; }
        await update(found[0].id, {
          first_name: row.nombre,
          last_name:  `${row.apellido1} ${row.apellido2}`.trim(),
          email:      row.correo   || null,
          phone:      row.telefono || null,
          role,
          type:       null,
          group_id:   null,
          active:     true,
        });
        results.updated++;
      } else if (['eliminar', 'delete', 'borrar'].includes(accion)) {
        const { rows: found } = await db.query('SELECT id FROM users WHERE id_number = $1', [row.cedula]);
        if (!found[0]) { results.errors.push({ row: row.cedula, error: 'Not found for delete' }); continue; }
        await deactivate(found[0].id);
        results.deactivated++;
      } else {
        results.skipped++;
      }
    } catch (err) {
      if (err.code === '23505') {
        results.skipped++;
      } else {
        results.errors.push({ row: row.cedula, error: err.message });
      }
    }
  }

  fs.unlinkSync(filePath);
  return results;
}

// CSV import: Students — formato Caleb: cedula;nombre;apellido1;apellido2;nivel;seccion;cedula_padre;accion
async function importStudentsFromCSV(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const records = parse(content, { columns: true, skip_empty_lines: true, trim: true, delimiter: ';' });

  const results = { created: 0, updated: 0, deactivated: 0, linked: 0, skipped: 0, errors: [] };

  async function resolveGroup(nivel, seccion) {
    if (!nivel || !seccion) return null;
    const { rows } = await db.query(
      'SELECT id FROM groups WHERE level = $1 AND name = $2',
      [nivel, seccion]
    );
    return rows[0]?.id || null;
  }

  for (const row of records) {
    const accion = (row.accion || '').trim().toLowerCase();

    try {
      if (['insertar', 'insert', 'crear'].includes(accion)) {
        const group_id = await resolveGroup(row.nivel, row.seccion);
        const student = await create({
          id_number:  row.cedula,
          first_name: row.nombre,
          last_name:  `${row.apellido1} ${row.apellido2}`.trim(),
          role:       'student',
          group_id,
        });
        results.created++;

        if (row.cedula_padre) {
          const { rows: parentRows } = await db.query(
            'SELECT id FROM users WHERE id_number = $1 AND role = $2 AND active = true',
            [row.cedula_padre, 'parent']
          );
          if (parentRows[0]) {
            await db.query(
              'INSERT INTO parent_students (parent_id, student_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
              [parentRows[0].id, student.id]
            );
            results.linked++;
          }
        }
      } else if (['update', 'actualizar', 'modificar'].includes(accion)) {
        const { rows: found } = await db.query('SELECT id FROM users WHERE id_number = $1', [row.cedula]);
        if (!found[0]) { results.errors.push({ row: row.cedula, error: 'Not found for update' }); continue; }
        const group_id = await resolveGroup(row.nivel, row.seccion);
        await update(found[0].id, {
          first_name: row.nombre,
          last_name:  `${row.apellido1} ${row.apellido2}`.trim(),
          email:      null,
          phone:      null,
          role:       'student',
          type:       null,
          group_id,
          active:     true,
        });
        results.updated++;
      } else if (['eliminar', 'delete', 'borrar'].includes(accion)) {
        const { rows: found } = await db.query('SELECT id FROM users WHERE id_number = $1', [row.cedula]);
        if (!found[0]) { results.errors.push({ row: row.cedula, error: 'Not found for delete' }); continue; }
        await deactivate(found[0].id);
        results.deactivated++;
      } else {
        results.skipped++;
      }
    } catch (err) {
      if (err.code === '23505') {
        results.skipped++;
      } else {
        results.errors.push({ row: row.cedula, error: err.message });
      }
    }
  }

  fs.unlinkSync(filePath);
  return results;
}

module.exports = {
  getAll, getById, create, update, deactivate,
  getSubjects, createSubject, getGroups, getChildren,
  getStudentSubjects, assignSubjectsToStudent, removeStudentSubject,
  importUsersFromCSV, importStudentsFromCSV,
};
