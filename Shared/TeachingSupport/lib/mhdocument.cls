\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{mhdocument}
  [2026/10/11 v0.6.1 MathHouse document class]

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Framework options
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Document type
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\DeclareOption{document}{%
  \PassOptionsToPackage{document}{mh}%
}

\DeclareOption{manual}{%
  \PassOptionsToPackage{manual}{mh}%
}

\DeclareOption{assessment}{%
  \PassOptionsToPackage{assessment}{mh}%
}

\DeclareOption{exam}{\ClassError{mhdocument}{Use assessment instead of exam}{The temporary exam option was removed.}}

\DeclareOption{worksheet}{%
  \PassOptionsToPackage{worksheet}{mh}%
}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Output mode
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\DeclareOption{student}{%
  \PassOptionsToPackage{student}{mh}%
}

\DeclareOption{solutions}{%
  \PassOptionsToPackage{solutions}{mh}%
}

\DeclareOption{developer}{%
  \PassOptionsToPackage{developer}{mh}%
}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Accessibility
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\DeclareOption{standard}{%
  \PassOptionsToPackage{standard}{mh}%
}

\DeclareOption{accessible}{%
  \PassOptionsToPackage{accessible}{mh}%
}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Other options
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Pass all other options to the underlying book class.
\DeclareOption*{%
  \PassOptionsToClass{\CurrentOption}{book}%
}

\ProcessOptions\relax

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Base class
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\LoadClass[
  11pt,
  openany,
  oneside
]{book}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% MathHouse framework
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\RequirePackage{mh}

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Standard-build support
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\IfMathAccessibleF{%
  % PGF 3.1.11a compatibility: accept TikZ alt text but ignore it.
  \tikzset{alt/.code={}}

  \RequirePackage{tocloft}
}

% Do not stretch vertical spaces to force every page to equal height.
\raggedbottom

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% Manual document structure
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\IfMathManualT{%

  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
  % Table of contents formatting
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

  \IfMathAccessibleF{%
    \renewcommand{\cftchappresnum}{Ch.\ }
    \renewcommand{\cftchapaftersnum}{:\ }
    \setlength{\cftchapnumwidth}{4.2em}
    \renewcommand{\cftchapleader}{\cftdotfill{\cftdotsep}}
    \renewcommand{\cftdotsep}{1}
  }

  \setcounter{secnumdepth}{0}
  \setcounter{tocdepth}{1}

  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
  % Title, contents, and matter transitions
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

  \makeatletter

  % Compact title block that shares its page with the table of contents.
  \renewcommand{\maketitle}{%
    \thispagestyle{mhfront}%
    \begin{center}
      \vspace*{0.35in}%
      {\Huge\bfseries \MathCenterHeader\par}
      \vspace{0.25in}%
      {\Large \MathLeftHeader\par}
      \vspace{0.12in}%
      {\large \MathRightHeader\par}
    \end{center}%
    \vspace{0.4in}%
  }

  % Keep the short contents list on the title page.
  \renewcommand{\tableofcontents}{%
    \par
    \vspace{0.35in}%
    {\Large\bfseries \contentsname\par}
    \vspace{0.15in}%
    \@starttoc{toc}%
    \thispagestyle{mhfront}%
    \clearpage
  }

  \renewcommand{\frontmatter}{%
    \@mainmatterfalse
    \pagenumbering{arabic}%
    \pagestyle{empty}%
  }

  \renewcommand{\mainmatter}{%
    \thispagestyle{mhfront}%
    \clearpage
    \@mainmattertrue
    \pagestyle{fancy}%
  }

  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
  % Chapter headings
  %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

  % Numbered chapters appear on one line directly below the running header.
  \renewcommand{\@makechapterhead}[1]{%
    {%
      \parindent\z@
      \raggedright
      \normalfont
      \LARGE\bfseries
      \chaptername\ \thechapter: #1\par
      \nobreak
      \vspace{2pt}%
      \hrule height 0.4pt
      \nobreak
      \vspace{10pt}%
    }%
  }

  % Unnumbered chapters use the same compact style without a chapter label.
  \renewcommand{\@makeschapterhead}[1]{%
    {%
      \parindent\z@
      \raggedright
      \normalfont
      \LARGE\bfseries
      #1\par
      \nobreak
      \vspace{2pt}%
      \hrule height 0.4pt
      \nobreak
      \vspace{10pt}%
    }%
  }

  \makeatother
}

\endinput
