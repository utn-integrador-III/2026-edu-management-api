const router     = require('express').Router();
const controller = require('./users.controller');
const { verifyToken }  = require('../../middleware/auth.middleware');
const { requireRole }  = require('../../middleware/role.middleware');
const multer           = require('multer');

const upload = multer({ dest: 'uploads/' });

router.use(verifyToken);

// Subjects
router.get('/subjects',  requireRole('admin', 'teacher'), controller.getSubjects);
router.post('/subjects', requireRole('admin'),            controller.createSubject);

// Groups
router.get('/groups', requireRole('admin', 'teacher'), controller.getGroups);

// Children of authenticated parent
router.get('/my-children', requireRole('parent'), controller.getMyChildren);

// RF-05: CRUD users (admin only)
router.get('/',       requireRole('admin'), controller.getAll);
router.post('/',      requireRole('admin'), controller.create);
router.get('/:id',    requireRole('admin'), controller.getById);
router.put('/:id',    requireRole('admin'), controller.update);
router.delete('/:id', requireRole('admin'), controller.deactivate);

// RF-06: Student subject assignment
router.get('/:id/subjects',               requireRole('admin', 'teacher'), controller.getStudentSubjects);
router.post('/:id/subjects',              requireRole('admin'),            controller.assignSubjectsToStudent);
router.delete('/:id/subjects/:subjectId', requireRole('admin'),            controller.removeStudentSubject);

// CSV import
router.post('/import/users',    requireRole('admin'), upload.single('file'), controller.importUsersCSV);
router.post('/import/students', requireRole('admin'), upload.single('file'), controller.importStudentsCSV);

module.exports = router;
