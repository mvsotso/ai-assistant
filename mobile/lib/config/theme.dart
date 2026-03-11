import 'package:flutter/material.dart';

class AppTheme {
  static const Color bg = Color(0xFF0B0F1A);
  static const Color surface = Color(0xFF131825);
  static const Color card = Color(0xFF1A1F2E);
  static const Color border = Color(0xFF2A3142);
  static const Color accent = Color(0xFF06B6D4);
  static const Color text = Color(0xFFE2E8F0);
  static const Color muted = Color(0xFF8892A6);
  static const Color green = Color(0xFF22C55E);
  static const Color orange = Color(0xFFF97316);
  static const Color red = Color(0xFFEF4444);
  static const Color purple = Color(0xFFA855F7);
  static const Color blue = Color(0xFF3B82F6);

  static final ThemeData darkTheme = ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: bg,
    primaryColor: accent,
    colorScheme: const ColorScheme.dark(
      primary: accent, secondary: purple, surface: surface, error: red,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: surface, elevation: 0, centerTitle: true,
      titleTextStyle: TextStyle(fontFamily: 'DM Sans', fontSize: 18, fontWeight: FontWeight.w600, color: text),
    ),
    cardTheme: CardTheme(
      color: card, elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: border)),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: surface, selectedItemColor: accent, unselectedItemColor: muted,
      type: BottomNavigationBarType.fixed,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true, fillColor: surface,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: border)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: border)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: accent)),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: accent, foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      ),
    ),
    fontFamily: 'DM Sans',
  );
}
