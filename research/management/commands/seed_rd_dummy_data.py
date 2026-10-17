import datetime
import random
from django.core.management.base import BaseCommand
from django.db import transaction
from users.models import UserDetails
from institution.models import Department
from research.models import FacultyResearchProject


RESEARCH_TEMPLATES = {
    'Computer Science': [
        {
            'title': 'AI-driven Diagnostic Framework for Crop Disease Identification from Leaf Spectrometry',
            'area': 'Artificial Intelligence & Computer Vision',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 1850000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Development of deep convolutional neural network models for real-time edge processing on low-power devices in agricultural fields.',
            'ref': 'https://ieeexplore.ieee.org/document/9847123'
        },
        {
            'title': 'Federated Learning on Edge IoT Devices for Secure Smart Campus Surveillance',
            'area': 'Distributed Systems & Cybersecurity',
            'type': 'Industry Sponsored',
            'agency': 'Tata Consultancy Services (TCS)',
            'amount': 1200000.00,
            'duration_months': 24,
            'status': 'Ongoing',
            'desc': 'Preserving privacy in distributed video streams using federated averaging algorithms and differential privacy.',
            'ref': 'https://sciencedirect.com/science/article/pii/S108480452300122X'
        },
        {
            'title': 'Automated Code Vulnerability Detection using Hybrid Graph Neural Networks',
            'area': 'Software Engineering & Deep Learning',
            'type': 'Funded',
            'agency': 'AICTE - RPS',
            'amount': 750000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Abstract Syntax Tree and Control Flow Graph embedding for static source code vulnerability detection.',
            'ref': 'https://springer.com/chapter/10.1007/978-3-030-84522-4_15'
        },
        {
            'title': 'Decentralized Healthcare Record Management utilizing Zero-Knowledge Proofs on Ethereum',
            'area': 'Blockchain & Cryptography',
            'type': 'Institutional',
            'agency': 'Institutional Research Seed Fund',
            'amount': 250000.00,
            'duration_months': 18,
            'status': 'Completed',
            'desc': 'Design and formal verification of gas-efficient smart contracts for inter-hospital EHR exchange.',
            'ref': 'https://ieeexplore.ieee.org/document/9123847'
        },
        {
            'title': 'Optimization of Transformer Architectures for Multilingual Natural Language Processing',
            'area': 'Natural Language Processing',
            'type': 'Non-Funded',
            'agency': None,
            'amount': 0.00,
            'duration_months': 12,
            'status': 'Proposed',
            'desc': 'Pruning and quantization of LLMs for low-resource Dravidian languages.',
            'ref': None
        }
    ],
    'Information Technology': [
        {
            'title': 'Cloud-Native Microservices Security Analysis using Behavioral Anomaly Detection',
            'area': 'Cloud Computing & Cyber Defense',
            'type': 'Funded',
            'agency': 'TNSCST',
            'amount': 450000.00,
            'duration_months': 24,
            'status': 'Ongoing',
            'desc': 'Real-time telemetry and eBPF tracing for zero-day exploit detection in Kubernetes container meshes.',
            'ref': 'https://ieeexplore.ieee.org/document/9981245'
        },
        {
            'title': 'Secure IoT Firmware Verification using Lightweight Cryptographic Primitives',
            'area': 'Embedded Security & IoT',
            'type': 'Consultancy',
            'agency': 'L&T Infotech Solutions',
            'amount': 600000.00,
            'duration_months': 18,
            'status': 'Completed',
            'desc': 'Silicon-level hardware root-of-trust verification protocol for industrial SCADA nodes.',
            'ref': 'https://sciencedirect.com/science/article/pii/S1389128623000891'
        },
        {
            'title': 'Semantic Search and Knowledge Graph Construction for Technical Academic Libraries',
            'area': 'Knowledge Engineering',
            'type': 'Institutional',
            'agency': 'Institutional Research Seed Fund',
            'amount': 180000.00,
            'duration_months': 12,
            'status': 'Completed',
            'desc': 'Graph-based ontology matching for automated syllabus and research indexing.',
            'ref': None
        }
    ],
    'Artificial Intelligence': [
        {
            'title': 'Explainable Deep Learning Models for Early Stage Diabetic Retinopathy Screening',
            'area': 'Medical Image Analysis & XAI',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 2200000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Grad-CAM and SHAP based interpretability pipelines for clinical decision support systems.',
            'ref': 'https://nature.com/articles/s41598-023-45678-x'
        },
        {
            'title': 'Autonomous Navigation Framework for Quadcopters in GPS-Denied Environments',
            'area': 'Robotics & Reinforcement Learning',
            'type': 'Funded',
            'agency': 'DRDO',
            'amount': 2600000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Visual-Inertial Odometry integrated with Proximal Policy Optimization for obstacle avoidance.',
            'ref': 'https://ieeexplore.ieee.org/document/9745129'
        },
        {
            'title': 'Predictive Maintenance of Industrial Wind Turbine Gearboxes using Temporal Fusion Transformers',
            'area': 'Predictive Analytics & Industrial AI',
            'type': 'Industry Sponsored',
            'agency': 'Siemens Energy Ltd',
            'amount': 1100000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Vibration and acoustic sensor fusion for early micro-crack fault prognosis.',
            'ref': 'https://sciencedirect.com/science/article/pii/S095183202300234X'
        }
    ],
    'Mechanical': [
        {
            'title': 'Optimization of Friction Stir Welding Parameters for Dissimilar Aerospace Grade Alloys',
            'area': 'Advanced Materials & Manufacturing',
            'type': 'Funded',
            'agency': 'DRDO',
            'amount': 1950000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Microstructural and tensile behavior analysis of AA7075 and Ti-6Al-4V welded joints.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0921509323011452'
        },
        {
            'title': 'CFD Investigation of Aerodynamic Drag Reduction in High-Speed Commercial Electric Buses',
            'area': 'Computational Fluid Dynamics',
            'type': 'Industry Sponsored',
            'agency': 'Ashok Leyland R&D Division',
            'amount': 850000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Rear vortex generators and active air curtains for 14% range extension in highway driving cycles.',
            'ref': 'https://saemobilus.sae.org/content/2023-01-0892'
        },
        {
            'title': 'Development of Bio-Degradable Polymeric Composites Reinforced with Chemically Treated Jute Fibers',
            'area': 'Green Composites & Polymer Engineering',
            'type': 'Funded',
            'agency': 'AICTE - RPS',
            'amount': 650000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Alkali-treated natural fiber reinforced matrices for automotive interior trim panels.',
            'ref': 'https://springer.com/article/10.1007/s10443-023-10112-8'
        },
        {
            'title': 'Performance Investigation of Phase Change Material in Hybrid Solar Water Desalination',
            'area': 'Thermal Engineering & Solar Energy',
            'type': 'Institutional',
            'agency': 'Institutional Research Seed Fund',
            'amount': 300000.00,
            'duration_months': 18,
            'status': 'Proposed',
            'desc': 'Paraffin wax thermal storage integration with stepped tubular solar stills.',
            'ref': None
        }
    ],
    'Civil': [
        {
            'title': 'Seismic Fragility Assessment of Retrofitted Multi-Storey Reinforced Concrete Buildings',
            'area': 'Structural Earthquake Engineering',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 1600000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Nonlinear push-over analysis and carbon fiber reinforced polymer (CFRP) column jacket optimization.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0141029623004561'
        },
        {
            'title': 'Experimental Study on Self-Compacting Geopolymer Concrete using Low-Calcium Fly Ash and GGBS',
            'area': 'Sustainable Construction Materials',
            'type': 'Funded',
            'agency': 'TNSCST',
            'amount': 500000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Zero-cement concrete formulations with sodium hydroxide-silicate activators curing at ambient temperature.',
            'ref': 'https://springer.com/article/10.1617/s11527-023-02115-0'
        },
        {
            'title': 'GIS-Based Hydrological Modeling for Flood Hazard Inundation and Urban Drainage Resilience',
            'area': 'Water Resources & Geoinformatics',
            'type': 'Consultancy',
            'agency': 'Tamil Nadu Municipal Administration',
            'amount': 720000.00,
            'duration_months': 18,
            'status': 'Completed',
            'desc': 'HEC-RAS 2D unsteady flow simulation for river basin catchment vulnerability mapping.',
            'ref': 'https://tandfonline.com/doi/full/10.1080/19475705.2023.2189012'
        },
        {
            'title': 'Stabilization of Expansive Black Cotton Soil using Nano-Silica and Industrial Steel Slag',
            'area': 'Geotechnical Engineering',
            'type': 'Non-Funded',
            'agency': None,
            'amount': 0.00,
            'duration_months': 12,
            'status': 'Proposed',
            'desc': 'CBR and unconfined compressive strength characteristics under cyclical wetting-drying.',
            'ref': None
        }
    ],
    'Electronics': [
        {
            'title': 'Low-Power VLSI Architecture Design for Real-Time Electrocardiogram Signal Compression',
            'area': 'VLSI & Biomedical Electronics',
            'type': 'Funded',
            'agency': 'AICTE - RPS',
            'amount': 900000.00,
            'duration_months': 24,
            'status': 'Ongoing',
            'desc': 'Sub-threshold adiabatic CMOS circuits for long-term wearable cardiac monitoring patches.',
            'ref': 'https://ieeexplore.ieee.org/document/9678124'
        },
        {
            'title': 'Design and Performance Optimization of Dual-Band Conformal Antenna for 5G Millimeter-Wave Terminals',
            'area': 'RF & Microwave Engineering',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 1400000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Electromagnetic bandgap (EBG) ground plane integration for high isolation and wide bandwidth at 28 GHz.',
            'ref': 'https://ieeexplore.ieee.org/document/9812456'
        },
        {
            'title': 'FPGA Hardware Acceleration of Convolutional Neural Networks for Edge Robotics',
            'area': 'Embedded VLSI & Computer Vision',
            'type': 'Industry Sponsored',
            'agency': 'Qualcomm Technologies',
            'amount': 1500000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Fixed-point systolic array hardware accelerator running on Xilinx Zynq UltraScale+ MPSOC.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0141933123001889'
        }
    ],
    'Electrical': [
        {
            'title': 'AI-Enhanced Maximum Power Point Tracking (MPPT) for Bifacial Solar Photovoltaic Systems',
            'area': 'Power Electronics & Renewable Energy',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 1350000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Particle Swarm Optimization combined with Deep Q-Networks under rapid partial shading conditions.',
            'ref': 'https://ieeexplore.ieee.org/document/9904123'
        },
        {
            'title': 'Design of Modular Multilevel Inverter with Fault-Tolerant Switching for Grid-Tied Storage',
            'area': 'Power Systems & Energy Storage',
            'type': 'Industry Sponsored',
            'agency': 'Schneider Electric India',
            'amount': 980000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Sub-module bypass circuitry and nearest level modulation for low Total Harmonic Distortion (THD).',
            'ref': 'https://sciencedirect.com/science/article/pii/S037877962300245X'
        },
        {
            'title': 'Bidirectional On-Board EV Charger with Vehicle-to-Grid (V2G) Reactive Power Support',
            'area': 'Electric Vehicles & Smart Grid',
            'type': 'Funded',
            'agency': 'TNSCST',
            'amount': 480000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Dual active bridge converter topologies with GaN power transistors achieving 96.5% peak efficiency.',
            'ref': 'https://ieeexplore.ieee.org/document/9512389'
        }
    ],
    'Agricultural': [
        {
            'title': 'IoT-Enabled Autonomous Precision Irrigation and Soil Nutrient Telemetry System',
            'area': 'Smart Agriculture & Sensor Networks',
            'type': 'Funded',
            'agency': 'DST-SERB',
            'amount': 1750000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'LoRaWAN based soil NPK and volumetric moisture monitoring with automated valve control.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0168169923003124'
        },
        {
            'title': 'Development of Solar-Powered Hydroponic Vertical Farming Infrastructure for Semi-Arid Regions',
            'area': 'Agro-Energy & Controlled Environment',
            'type': 'Funded',
            'agency': 'TNSCST',
            'amount': 600000.00,
            'duration_months': 24,
            'status': 'Completed',
            'desc': 'Closed-loop nutrient film technique (NFT) with automated pH balancing and microclimatic evaporative cooling.',
            'ref': 'https://springer.com/article/10.1007/s40093-023-00588-4'
        },
        {
            'title': 'Automated Post-Harvest Paddy Grain Quality Grading using Multispectral Computer Vision',
            'area': 'Food Engineering & Machine Vision',
            'type': 'Institutional',
            'agency': 'Institutional Research Seed Fund',
            'amount': 220000.00,
            'duration_months': 12,
            'status': 'Proposed',
            'desc': 'Identification of broken grains, discolored kernels, and moisture content from NIR imagery.',
            'ref': None
        }
    ],
    'Science': [
        {
            'title': 'Synthesis and Characterization of Novel Zinc Oxide Nanoparticles for Photocatalytic Water Purification',
            'area': 'Nanotechnology & Environmental Chemistry',
            'type': 'Funded',
            'agency': 'CSIR',
            'amount': 1100000.00,
            'duration_months': 36,
            'status': 'Ongoing',
            'desc': 'Green synthesis using plant extracts and solar-driven degradation of toxic industrial azo dyes.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0925838823005671'
        },
        {
            'title': 'Mathematical Modeling of Non-Newtonian Boundary Layer Fluid Flow with Thermal Radiation',
            'area': 'Applied Mathematics & Fluid Dynamics',
            'type': 'Non-Funded',
            'agency': None,
            'amount': 0.00,
            'duration_months': 18,
            'status': 'Completed',
            'desc': 'Numerical solutions using Runge-Kutta Fehlberg method for Casson fluid flow past stretching sheets.',
            'ref': 'https://springer.com/article/10.1007/s40096-023-00512-1'
        }
    ],
    'Management': [
        {
            'title': 'Impact of Green Supply Chain Strategies on Operational Performance in Manufacturing MSMEs',
            'area': 'Sustainable Operations Management',
            'type': 'Consultancy',
            'agency': 'CII - Southern Region',
            'amount': 350000.00,
            'duration_months': 12,
            'status': 'Completed',
            'desc': 'Structural equation modeling (SEM) analysis of carbon footprint abatement across 120 auto-ancillary units.',
            'ref': 'https://sciencedirect.com/science/article/pii/S0959652623014567'
        },
        {
            'title': 'Deep Reinforcement Learning for Algorithmic Trading and Quantitative Portfolio Optimization',
            'area': 'Financial Technology & Quantitative Finance',
            'type': 'Institutional',
            'agency': 'Institutional Research Seed Fund',
            'amount': 150000.00,
            'duration_months': 12,
            'status': 'Proposed',
            'desc': 'Actor-Critic agents dynamic asset rebalancing on National Stock Exchange (NSE) indices.',
            'ref': None
        }
    ]
}

EXTERNAL_CO_INVESTIGATORS_POOL = [
    {'name': 'Dr. K. S. Raman', 'affiliation': 'Department of Computer Science, Anna University, Chennai'},
    {'name': 'Prof. M. Vijayalakshmi', 'affiliation': 'Centre for Aerospace Research, MIT Campus, Chennai'},
    {'name': 'Dr. S. Sundaramurthy', 'affiliation': 'School of Electrical Sciences, IIT Madras'},
    {'name': 'Dr. R. Anuradha', 'affiliation': 'Structural Engineering Research Centre (CSIR-SERC), Chennai'},
    {'name': 'Prof. T. Balakrishnan', 'affiliation': 'Tamil Nadu Agricultural University (TNAU), Coimbatore'},
    {'name': 'Dr. N. Hemalatha', 'affiliation': 'Department of Physics, Indian Institute of Science (IISc), Bangalore'},
    {'name': 'Dr. G. Sivakumar', 'affiliation': 'National Institute of Technology (NIT), Tiruchirappalli'},
]


class Command(BaseCommand):
    help = 'Seeds realistic Faculty Research & Development (R&D) projects and papers for faculty across departments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing FacultyResearchProject records before seeding',
        )

    def handle(self, *args, **options):
        if options.get('clear'):
            count = FacultyResearchProject.objects.count()
            FacultyResearchProject.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing research project records."))

        departments = list(Department.objects.all())
        if not departments:
            self.stdout.write(self.style.ERROR("No departments found in the system. Please set up departments first."))
            return

        total_created = 0
        current_year = datetime.date.today().year

        with transaction.atomic():
            for dept in departments:
                dept_name = dept.department_name
                
                # Find matching templates
                matched_key = None
                for key in RESEARCH_TEMPLATES:
                    if key.lower() in dept_name.lower():
                        matched_key = key
                        break
                if not matched_key:
                    # Fallback to Computer Science or Science
                    matched_key = 'Computer Science' if 'engineering' in dept_name.lower() or 'technology' in dept_name.lower() else 'Science'

                templates = RESEARCH_TEMPLATES.get(matched_key, RESEARCH_TEMPLATES['Computer Science'])

                # Find faculty in this department
                dept_faculty = list(
                    UserDetails.objects.filter(department=dept)
                    .exclude(user__role__role_name__iexact='STUDENT')
                    .select_related('user')
                )

                if not dept_faculty:
                    continue

                dept_code_clean = (dept.department_code or dept_name[:3]).upper().replace(' ', '')

                for idx, tmpl in enumerate(templates):
                    pi = dept_faculty[idx % len(dept_faculty)]
                    
                    # Pick 1-2 co-investigators if available
                    other_faculty = [f for f in dept_faculty if f.id != pi.id]
                    co_pis = random.sample(other_faculty, min(len(other_faculty), random.randint(1, 2))) if other_faculty else []

                    # Pick 1 external co-investigator
                    external_co = [random.choice(EXTERNAL_CO_INVESTIGATORS_POOL)] if random.random() > 0.3 else []

                    # Calculate realistic dates
                    dur = tmpl['duration_months']
                    if tmpl['status'] == 'Completed':
                        start_date = datetime.date(current_year - 3, random.randint(1, 6), 15)
                        end_date = start_date + datetime.timedelta(days=dur * 30)
                    elif tmpl['status'] == 'Ongoing':
                        start_date = datetime.date(current_year - 1, random.randint(1, 9), 1)
                        end_date = start_date + datetime.timedelta(days=dur * 30)
                    else:  # Proposed
                        start_date = datetime.date(current_year, random.randint(1, 10), 1)
                        end_date = start_date + datetime.timedelta(days=dur * 30)

                    project_code = f"TEC/RD/{dept_code_clean}/{start_date.year}/{idx + 1:03d}"

                    # Create or update project
                    project, created = FacultyResearchProject.objects.update_or_create(
                        project_code=project_code,
                        defaults={
                            'project_title': tmpl['title'],
                            'principal_investigator': pi,
                            'external_co_investigators': external_co,
                            'research_area': tmpl['area'],
                            'project_type': tmpl['type'],
                            'funding_agency': tmpl['agency'],
                            'sanctioned_amount': tmpl['amount'],
                            'project_start_date': start_date,
                            'project_end_date': end_date,
                            'status': tmpl['status'],
                            'description': tmpl['desc'],
                            'objectives': f"1. Comprehensive investigation into {tmpl['area'].lower()}.\n2. Prototype development and experimental validation.\n3. Research paper publication in indexed Q1/Q2 journals.",
                            'outcomes': f"High-impact technical publications, student research fellowships, and institutional patent filing.",
                            'site_name': 'Thirumalai Engineering College R&D Hub',
                            'reference_url': tmpl['ref'],
                            'created_by': pi.user if pi.user else None,
                            'updated_by': pi.user if pi.user else None,
                        }
                    )

                    if co_pis:
                        project.co_investigators.set(co_pis)

                    total_created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully seeded {total_created} Faculty R&D projects/papers across {len(departments)} departments!")
        )
