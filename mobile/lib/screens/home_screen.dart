import 'package:flutter/material.dart';
import '../config/theme.dart';
import 'dashboard_screen.dart';
import 'task_list_screen.dart';
import 'ai_chat_screen.dart';
import 'calendar_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;

  final _screens = const [
    DashboardScreen(),
    TaskListScreen(),
    AIChatScreen(),
    CalendarScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: _screens),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (i) => setState(() => _currentIndex = i),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'Dashboard'),
          BottomNavigationBarItem(icon: Icon(Icons.task_alt), label: 'Tasks'),
          BottomNavigationBarItem(icon: Icon(Icons.smart_toy), label: 'AI Chat'),
          BottomNavigationBarItem(icon: Icon(Icons.calendar_month), label: 'Calendar'),
        ],
      ),
    );
  }
}
