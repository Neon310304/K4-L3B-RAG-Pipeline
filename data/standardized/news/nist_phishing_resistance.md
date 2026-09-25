---
id: nist_phishing_resistance
url: https://www.nist.gov/blogs/cybersecurity-insights/phishing-resistance-protecting-keys-your-kingdom
title: Phishing Resistance – Protecting the Keys to Your Kingdom
date_crawled: '2026-09-25T04:15:00+00:00'
date_published: 2023-02-01T07:00-05:00
date_modified: 2025-04-09T09:29-04:00
doc_type: news
publisher: NIST
language: en
content_sha256: 1919bc8d58343b117e5aee9769546c9490a07ee90043f050bd75da6a449371fe
license: 'NIST public information: copying/distribution permitted except material
  marked copyrighted; source attribution retained. Article images excluded.'
license_url: https://www.nist.gov/copyrights-disclaimers
extraction: First .text-with-summary; no navigation, bios, comments, images or embedded
  media
resolved_url: https://www.nist.gov/blogs/cybersecurity-insights/phishing-resistance-protecting-keys-your-kingdom
source: nist_phishing_resistance.json
landing_file: data/landing/news/nist_phishing_resistance.json
landing_sha256: ca849aa54c6a84085abaf7e2c50298b7f35813515566837487dc868078dfa525
---

# Phishing Resistance – Protecting the Keys to Your Kingdom

If you own a computer, watch the news, or spend virtually any time online these days you have probably heard the term “phishing.” Never in a positive context…and possibly because you have been a victim yourself.

Phishing refers to a variety of attacks that are intended to convince you to forfeit sensitive data to an imposter. These attacks can take a number of different forms; from spear-phishing (which targets a specific individual within an organization), to whaling (which goes one step further and targets senior executives or leaders). Furthermore, phishing attacks take place over multiple channels or even across channels; from the more traditional email-based attacks to those using voice – vishing – to those coming via text message – smishing. Regardless of the type or channel, the intent of the attack is the same – to exploit human nature to gain control of sensitive information (*citation 1).* These attacks typically make use of several techniques including impersonated websites, attacker-in-the-middle, and relay or replay to achieve their desired outcome.

Due to their effectiveness and simplicity, phishing attacks have rapidly become the tool of choice for baddies everywhere. As a tactic, it is used by everyone from low level criminals looking to commit fraud, to the sophisticated nation state attackers seeking a foothold within an enterprise network. And, while almost any kind of information can be targeted, often the most damaging attacks focus on your password, pin, or one-time passcodes – the keys to your digital realm. The combination can be catastrophic. The Verizon 2022 Data Breach Investigations Report lists phishing and stolen credentials (which may be harvested during  phishing attacks) as two of the four “key pathways” that organizations must be prepared to address in order to prevent breaches (*citation 2)*. In recognition of the threat posed by phishing – the Office of Management and Budget’s [Memo 22-09](https://bidenwhitehouse.archives.gov/wp-content/uploads/2022/01/M-22-09.pdf) “Moving the U.S. Government Toward Zero Trust Cybersecurity Principles” prioritizes implementation of phishing resistant authenticators (*citation 3)*.   

So – how do you keep your keys from falling into the wrong hands?  What constitutes a phishing resistant authenticator? NIST Special Publication DRAFT 800-63-B4 defines it as “the ability of the authentication protocol to detect and prevent disclosure of authentication secrets and valid authenticator outputs to an impostor relying party without reliance on the vigilance of the subscriber.” To achieve this, phishing resistant authenticators must address the following attack vectors associated phishing:

- **Impersonated Websites** – Phishing resistant authenticators prevent the use of authenticators at illegitimate websites (known as verifiers) through multiple cryptographic measures. This is achieved through the establishment of authenticated protected channels for communications and methods to restrict the context of an authenticator’s use. For example, this may be achieved through name binding – where an authenticator is only valid for a specific domain (*I can only use this for one website*). It may also be achieved through binding to a communication channel – such as in client authenticated TLS (*I can only use this over a specific connection*).
- **Attacker-in-the Middle -** Phishing resistant authenticators prevent an attacker-in-the-middle from capturing authentication data from the user and relaying it to the relying website. This is achieved through cryptographic measures, such as leveraging an authenticated protected channel for the exchange of information and digitally signing authentication data and messages.
- **User Entry** – Phishing resistant authenticators eliminate the need for a user to type or manually input authentication data over the internet. This is achieved through the use of cryptographic keys for authentication that are unlocked locally through a biometric or pin. No *user entered information* is exchanged between the relying website and the authenticator itself.
- **Replay** – Phishing resistant authenticators prevent attackers from using captured authentication data at a later point in time. Supporting cryptographic controls for restricting context and to prevent attacker-in-the-middle scenarios are also preventative of replay attacks, particularly digitally signed and time-stamped authentication and message data.

As complicated as this may seem, there are several practical examples of phishing resistant authenticators in place today. For U.S. federal employees, the most ubiquitous form of phishing resistant authenticator is the Personal Identity Verification (PIV) card; they leverage public-key cryptography to protect authentication events. Commercially, FIDO authenticators paired with W3C’s Web Authentication API are the most common form of phishing resistant authenticators widely available today. These can take the form of separate hardware keys or be embedded directly into platforms (for example your phone or laptop). Availability, practicality, and security of these “platform authenticators” increasingly puts strong, phishing resistant authenticators into user’s hands without the need for additional form factors or dongles.

Not every transaction *requires* phishing resistant authenticators. However, for applications that protect sensitive information (such as health information or confidential client data) or for users that have elevated privileges (such as admins or security personnel) organizations should be enforcing, or at least offering, phishing resistant authenticators. Individuals should explore the security settings for their more sensitive online accounts to see if phishing resistant authenticators are available and make use of them if they are. In reality, these tools are often easier, faster, and more convenient than the MFA – such as SMS text codes – they may currently be using.

In the end, phishing resistant authenticators are a critical tool in personal and enterprise security that should be embraced and adopted. They are not, however, a silver bullet. Phishing resistant authenticators only address one focus of phishing attacks – the compromise and re-use of authenticators such as passwords and one-time passcodes. They do not mitigate phishing attempts that may have alternative goals such as installing malware or compromising personal information to be used elsewhere. Phishing resistant authenticators should be paired with a comprehensive phishing prevention program that includes user awareness and training, email protection controls, data loss prevention tools, and network security capabilities.

For more information on phishing resistant authenticators, please read and comment on our [Draft Fourth Revision of NIST SP 800-63, *Digital Identity Guideline*](https://csrc.nist.gov/publications/detail/sp/800-63/4/draft)*s* by **11:59pm on Friday, March 24, 2023.**  

Also, check out our [Phish Scale](https://www.nist.gov/video/introducing-phish-scale "Introducing Phish Scale ") and [Protecting Your Small Business: Phishing](https://www.nist.gov/video/protecting-your-small-business-phishing "Protecting Your Small Business: Phishing") videos!

---

**Citations:**  

1. Acheampong, I.K. June 2019. *The State of Phishing Attack Vector*. OWASP Ghana Chapter. <https://github.com/OWASP/www-chapter-ghana/blob/master/assets/slides/Phishing_Presentation(OWASP_Ghana).pdf>

2. Verizon. *Data Breach Investigations Report*. Retrieved January 19th, 2023, from <https://www.verizon.com/business/en-gb/resources/2022-data-breach-investigations-report-dbir.pdf>   
3. <https://bidenwhitehouse.archives.gov/wp-content/uploads/2022/01/M-22-09.pdf>
