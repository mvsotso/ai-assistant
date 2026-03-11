import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../services/auth_service.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool _loading = false;

  Future<void> _signIn() async {
    setState(() => _loading = true);
    final result = await AuthService.signIn();
    setState(() => _loading = false);
    if (result != null && mounted) {
      Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const HomeScreen()));
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Sign in failed. Please try again.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 80, height: 80,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [AppTheme.accent, AppTheme.purple]),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Icon(Icons.smart_toy, size: 40, color: Colors.white),
              ),
              const SizedBox(height: 24),
              const Text('AI Assistant', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: AppTheme.text)),
              const SizedBox(height: 8),
              const Text('Personal AI-Powered Task Manager', style: TextStyle(fontSize: 14, color: AppTheme.muted)),
              const SizedBox(height: 48),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _loading ? null : _signIn,
                  icon: _loading
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.login),
                  label: Text(_loading ? 'Signing in...' : 'Sign in with Google'),
                  style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
