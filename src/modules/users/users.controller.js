const usersService = require('./users.service');

// RF-05
async function getAll(req, res) {
  try {
    const filters = {};
    if (req.query.role)   filters.role   = req.query.role;
    if (req.query.active) filters.active = req.query.active === 'true';
    res.json(await usersService.getAll(filters));
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

async function getById(req, res) {
  try {
    const user = await usersService.getById(req.params.id);
    if (!user) return res.status(404).json({ message: 'User not found' });
    res.json(user);
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

async function create(req, res) {
  try {
    const { id_number, first_name, last_name, role } = req.body;
    if (!id_number || !first_name || !last_name || !role) {
      return res.status(400).json({ message: 'id_number, first_name, last_name and role are required' });
    }
    const user = await usersService.create(req.body);
    res.status(201).json(user);
  } catch (err) {
    if (err.code === '23505') {
      return res.status(409).json({ message: 'A user with that ID number or email already exists' });
    }
    res.status(400).json({ message: err.message });
  }
}

async function update(req, res) {
  try {
    const user = await usersService.update(req.params.id, req.body);
    res.json(user);
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

async function deactivate(req, res) {
  try {
    await usersService.deactivate(req.params.id);
    res.json({ message: 'User deactivated' });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

// Subjects
async function getSubjects(_req, res) {
  try {
    res.json(await usersService.getSubjects());
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

async function createSubject(req, res) {
  try {
    const { name, code } = req.body;
    if (!name || !code) {
      return res.status(400).json({ message: 'name and code are required' });
    }
    const subject = await usersService.createSubject(req.body);
    res.status(201).json(subject);
  } catch (err) {
    if (err.code === '23505') {
      return res.status(409).json({ message: 'A subject with that code already exists' });
    }
    res.status(400).json({ message: err.message });
  }
}

// Groups
async function getGroups(_req, res) {
  try {
    res.json(await usersService.getGroups());
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

// Children of parent
async function getMyChildren(req, res) {
  try {
    res.json(await usersService.getChildren(req.user.id));
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

// RF-06
async function getStudentSubjects(req, res) {
  try {
    res.json(await usersService.getStudentSubjects(req.params.id, req.query.period));
  } catch (err) {
    res.status(500).json({ message: err.message });
  }
}

async function assignSubjectsToStudent(req, res) {
  try {
    const { assignments } = req.body;
    if (!Array.isArray(assignments) || assignments.length === 0) {
      return res.status(400).json({ message: 'assignments must be a non-empty array' });
    }
    await usersService.assignSubjectsToStudent(req.params.id, assignments);
    res.json({ message: 'Subjects assigned successfully' });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

async function removeStudentSubject(req, res) {
  try {
    await usersService.removeStudentSubject(req.params.id, req.params.subjectId, req.query.period);
    res.json({ message: 'Subject removed from student' });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

// CSV import
async function importUsersCSV(req, res) {
  try {
    if (!req.file) return res.status(400).json({ message: 'CSV file is required' });
    const result = await usersService.importUsersFromCSV(req.file.path);
    res.json(result);
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

async function importStudentsCSV(req, res) {
  try {
    if (!req.file) return res.status(400).json({ message: 'CSV file is required' });
    const result = await usersService.importStudentsFromCSV(req.file.path);
    res.json(result);
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
}

module.exports = {
  getAll, getById, create, update, deactivate,
  getSubjects, createSubject, getGroups, getMyChildren,
  getStudentSubjects, assignSubjectsToStudent, removeStudentSubject,
  importUsersCSV, importStudentsCSV,
};
