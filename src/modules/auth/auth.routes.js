const router     = require('express').Router();
const controller = require('./auth.controller');
const { verifyToken } = require('../../middleware/auth.middleware');

router.post('/login',           controller.login);                       // RF-01
router.post('/change-password', verifyToken, controller.changePassword); // RF-02
router.post('/forgot-password', controller.forgotPassword);              // RF-03
router.post('/reset-password',  controller.resetPassword);               // RF-03
router.post('/logout',          verifyToken, controller.logout);         // RF-04

module.exports = router;
