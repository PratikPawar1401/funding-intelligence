import type { Metadata } from "next";
import { Inter, Montserrat } from "next/font/google";
import "./globals.css";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import { ThemeProvider } from "@/components/layout/theme-provider";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

// Free equivalent to issr.ua.edu's Proxima Nova (Adobe Typekit, paid, not
// bundleable into this public repo). Montserrat's condensed-adjacent
// character stands in for Proxima Nova Condensed on headings; Inter is a
// clean, widely-used body pairing.
const montserrat = Montserrat({
  variable: "--font-heading",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "ISSR Funding Intelligence | Simpler Grants.gov",
  description:
    "AI-Powered Funding Opportunity Discovery for the Institute for Social Science Research.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${montserrat.variable} ${inter.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full font-sans">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {/* defaultOpen=false: hidden until the hamburger (SidebarTrigger,
              in Topbar) opens it -- not a persistent column. */}
          <SidebarProvider defaultOpen={false}>
            <SidebarNav />
            <SidebarInset>{children}</SidebarInset>
          </SidebarProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
